import re
import os
from enum import Enum
from typing import List, Tuple, Dict, Optional
from openai import OpenAI
from openai.types.chat import ChatCompletion

from utils.actionType import DeFiActionType
# 如果不需要本地模型，可以注释掉下面这行
# from utils.gen_with_local_model import generate_completion 

class Tendency(Enum):
    INCREASE = "Increase"
    DECREASE = "Decrease"
    UNCERTAIN = "Uncertain"

class PriceChangeInferenceKey:
    def __init__(self, defiActionType: DeFiActionType | List[DeFiActionType], manipulated_pool: str) -> None:
        self.defiActionType = defiActionType
        self.manipulated_pool = manipulated_pool
    
    def debug_log(self) -> None:
        if isinstance(self.defiActionType, list):
            print("[i] DeFi action type: ", [actionType.value for actionType in self.defiActionType])
        else:
            print("[i] DeFi action type: ", self.defiActionType.value)
        print("[i] Manipulated pool: ", self.manipulated_pool)
    
    def debug_store_data(self) -> Dict:
        if isinstance(self.defiActionType, list):
            defiActionType = [actionType.value for actionType in self.defiActionType]
        else:
            defiActionType = self.defiActionType.value
        return {
            "defiActionType": defiActionType,
            "manipulated_pool": self.manipulated_pool
        }

class PriceChangeInferenceUnit:
    def __init__(self, 
                 pool_address: str, 
                 token_address_list: List[str], 
                 code_snippet: Optional[str], 
                 variables_change: Dict[str, Dict[str, int]],
                 contract_name_mapping: Dict[str, str],
                 token_name_mapping: Dict[str,str],
                 model,
                 tokenizer,
                 device) -> None:
        self.contract_name_mapping = contract_name_mapping
        self.token_name_mapping = token_name_mapping
        self.pool_address = pool_address
        self.token_address_list = token_address_list
        self.code_snippet = code_snippet
        self.variables_change = variables_change
        self.model = model
        self.tokenizer = tokenizer
        self.device = device
        self.price_change_inference = self.generate_price_change_inference()
    
    def generate_prompt(self) -> Tuple[str, List[str]]:
        statements = self.generate_statements()
        variables_change_prompt = self.generate_variable_change()
        answer_format = self.generate_answer_format(statements)

        answer_template = """
You must follow the following format(delimited with XML tags) to answer the question and replace {score} with your evaluation scores.
<answer>
{answer_format}
</answer>
        """.format(BASE_TOKEN="{BASE_TOKEN}" ,score="{score}", answer_format=("\n").join(answer_format))

        if self.code_snippet:
            instruction_1 = "\nInstruction 1:\nThe following is related price calculation functions. You are required to extract the price calculation model.\n"
            intruction_2 = "\nInstruction 2:\nYou will be provided with some changes of variables in the price calculation model(delimited with XML tags). Only based on the price model you extracted previously and the following change, evaluate the degree of credibility of following statements and give me evaluation scores from 1 to 10: {statements}. There is no need for quantitative calculation. Do not need to consider the effect of the market, supply and demand model\n".format(statements=(" ").join(statements))
            prompt = instruction_1 + self.code_snippet + intruction_2 + variables_change_prompt + answer_template
        else:
            instruction = "\n{pool_address} is the address of a liquidity pool. The price model of the pool aligns with the Constant Product Market Maker (CPMM). You will be provided with some changes of tokens' balance inside the pool. Only based on the given information, you are required to evaluate the degree of credibility of following statements and give me evaluation scores from 1 to 10: {statements}. There is no need for quantitative calculation. Do not need to consider the effect of the market, supply and demand model\n".format(pool_address=self.pool_address, statements=(" ").join(statements))
            prompt = instruction + variables_change_prompt + answer_template
        
        return (prompt, statements)

    def generate_price_change_inference(self) -> Dict[str, Tendency]:
        print("[+] Start price change inference")
        
        try:
            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                print("❌ Error: OPENAI_API_KEY environment variable is not set.")
                return {}

            client = OpenAI(api_key=api_key)

            retry = 0
            retry_limit = 2
            scores = []
            statements = []

            while retry <= retry_limit: 
                result = self.get_evaluation_score(client)
                (scores, statements, completion) = result
                
                if len(scores) != len(statements):
                    if retry < retry_limit:
                        print(f"[!] Scores mismatch, retrying ({retry + 1}/{retry_limit})...")
                        retry += 1
                    else:
                        scores = [0] * len(statements)
                        break
                else:
                    break
            
            return self.generate_finally_prediction(scores)

        except Exception as e:
            print(f"[!] Error in price inference: {e}")
            return {}

    def generate_statements(self) -> List[str]:
        statments = []
        token_list_len = len(self.token_address_list)
        pool_name = self.contract_name_mapping.get(self.pool_address, self.pool_address)
        
        for index, token_address in enumerate(self.token_address_list):
            token_name = self.token_name_mapping.get(token_address, token_address)
            relative_token = ""
            if token_list_len == 2:
                rel_addr = self.token_address_list[1 - index]
                rel_name = self.token_name_mapping.get(rel_addr, rel_addr)
                relative_token = f" relative to {rel_name}"
            
            statments.append(f"{index*2+1})The price of {token_name}{relative_token} in {pool_name} increases after change")
            statments.append(f"{index*2+2})The price of {token_name}{relative_token} in {pool_name} decreases after change")
        return statments

    def generate_variable_change(self) -> str:
        variable_change = []
        for contract_address, variables in self.variables_change.items():
            if contract_address in ["0x0000000000000000000000000000000000000000", "0x000000000000000000000000000000000000dEaD"]:
                for var_name, val in variables.items():
                    var_name = self.token_name_mapping.get(var_name, var_name)
                    if val > 0:
                        variable_change.append(f"The total supply of {var_name} decreases by {val}")
                    elif val < 0:
                        variable_change.append(f"The total supply of {var_name} increases by {-val}")
            else:
                c_name = self.contract_name_mapping.get(contract_address, contract_address)
                for var_name, val in variables.items():
                    var_name = self.token_name_mapping.get(var_name, var_name)
                    if val > 0:
                        variable_change.append(f"The balance of {var_name} in contract {c_name} increases by {val}")
                    elif val < 0:
                        variable_change.append(f"The balance of {var_name} in contract {c_name} decreases by {-val}")
        
        return "\n".join(["<change>"] + variable_change + ["</change>"])

    def get_evaluation_score(self, client: OpenAI) -> Tuple[List[int], List[str], ChatCompletion]:
        model = "gpt-4o"
        (prompt, statements) = self.generate_prompt()
        
        if not prompt:
            return ([0] * len(statements), statements, None)

        try:
            completion = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a DeFi security expert. Pay attention to oracle price calculations that rely on on-chain reserves or total supply, as they are vulnerable to flashloan manipulation. Even if source code is missing, infer potential manipulation from abnormal token balance changes in the pool."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0,
                top_p=1,
            )
            answer = completion.choices[0].message.content
            scores = self.extract_scores(answer, len(statements))
            return (scores, statements, completion)
        except Exception as e:
            print(f"[!] API Call Error: {e}")
            return ([0] * len(statements), statements, None)

    def extract_scores(self, completion: str, statement_len: int) -> List[int]:
        pattern = r"\d+\).*:(\s*\d+)" 
        scores = re.findall(pattern, completion)
        return [int(s) for s in scores[:statement_len]]

    def generate_answer_format(self, statements: List[str]) -> List[str]:
        return [f"{s.split(')')[0]}) Evaluation score of {s.split(')')[1]}: {{score}}" for s in statements]

    def generate_finally_prediction(self, scores: List[int]) -> Dict[str, Tendency]:
        print(f"📊 [LLM Score Result] {scores}")
        price_change_tendency = dict()
        CONFIDENCE_THRESHOLD = 6 
        
        for index, i in enumerate(range(0, len(scores) - 1, 2)):
            if index >= len(self.token_address_list): break
            
            inc, dec = scores[i], scores[i+1]
            token_addr = self.token_address_list[index]

            if inc > dec and inc >= CONFIDENCE_THRESHOLD:
                price_change_tendency[token_addr] = Tendency.INCREASE
            elif dec > inc and dec >= CONFIDENCE_THRESHOLD:
                price_change_tendency[token_addr] = Tendency.DECREASE
            else:
                price_change_tendency[token_addr] = Tendency.UNCERTAIN
        return price_change_tendency
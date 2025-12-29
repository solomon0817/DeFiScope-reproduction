import os
import re
import json
import shutil
import requests
from typing import List, Tuple, Optional
from solc_select import solc_select
from slither.slither import Slither
from slither.core.declarations import Contract
from utils.config import SUPPORTED_NETWORK

WHITE_LIST = ['SafeMath', 'PausableUpgradeable', 'OwnableUpgradeable', 'ContextUpgradeable', 'ReentrancyGuardUpgradeable', 'Initializable', 'AddressUpgradeable']
STANDARD_CONTRACTS = ['IERC20', 'BEP20', 'IBEP20', 'SafeBEP20', 'Address', 'SafeMath', 'Math', 'AccessControlledOffchainAggregator', 'EACAggregatorProxy']
PATTERN = re.compile(r"pragma solidity\s*(?:\^|>=|<=|=)?\s*(\d+\.\d+\.\d+)")

CONTRACT_CACHE = {} # Cache the contract file: {contract_address: contract_name}

class Function:
    def __init__(self, contract_address: str, entry_point: str, platform: str) -> None:
        # Prepare the contract
        self.contract_address = contract_address
        self.entry_point = entry_point
        self.contract_name = self.get_contract_name(platform=platform)
        (self.contract, self.slither) = self.get_contracts()
        # Extract the code snippet of the function
        self.filtered_functions = self.filter_modifiers_functions()
        self.contract_file_path = os.path.join("tmp",self.contract_address,self.contract_name+".sol")
        self.code_snippet = self.extract_functions_from_single_contract()

    def get_contract_name(self, platform: str) -> str:
        print("[i]Contract address: {contract_address}".format(contract_address=self.contract_address))
        if self.contract_address in CONTRACT_CACHE:
            print("[i]Contract name (get from cache): {contract_name}".format(contract_name=CONTRACT_CACHE[self.contract_address]))
            return CONTRACT_CACHE[self.contract_address]
        else:
            self.download_contracts(contract_address=self.contract_address, platform=platform)

            # --- V2 适配修改 (最终版) ---
            # 1. 设置 Headers 伪装浏览器 (关键修复)
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }

            # 2. 统一使用 Etherscan V2 接口 (因为 BscScan V1 已经废弃)
            v2_base_url = "https://api.etherscan.io/v2/api"
            
            # 3. 确定 Chain ID 和 API Key
            # 注意：V2 接口建议统一使用 Etherscan 的 API Key
            # 请确保 config.py 里 ethereum 的 api_key 是有效的 Etherscan Key
            if platform == "bsc":
                chain_id = "56"
                # 强制使用 Ethereum 的 Key (通常通用)，或者你新申请的通用 Key
                explorer_api_key = SUPPORTED_NETWORK["ethereum"]["api_key"]
            elif platform == "ethereum":
                chain_id = "1"
                explorer_api_key = SUPPORTED_NETWORK["ethereum"]["api_key"]
            elif platform == "fantom":
                chain_id = "250"
                explorer_api_key = SUPPORTED_NETWORK["ethereum"]["api_key"]
            else:
                # 如果有其他链，默认 fallback 到 ethereum key，或者你需要处理报错
                chain_id = "1" 
                explorer_api_key = SUPPORTED_NETWORK["ethereum"]["api_key"]

            # 4. 构造 V2 URL
            abi_endpoint = (
                f"{v2_base_url}?"
                f"chainid={chain_id}&"
                f"module=contract&action=getsourcecode&"
                f"address={self.contract_address}&"
                f"apikey={explorer_api_key}"
            )
            
            print(f"[i] Requesting: {abi_endpoint}") 

            try:
                # 5. 发送请求 (带 Headers 和 Timeout)
                response = requests.get(abi_endpoint, headers=headers, timeout=10)
                ret = json.loads(response.text)

                # --- 结果解析修复 ---
                result_data = ret.get("result", [])

                # 检查是否为列表且非空
                if isinstance(result_data, list) and len(result_data) > 0:
                    contract_name = result_data[0].get("ContractName", "Unknown")
                    # 有时候 API 会返回空名字
                    if not contract_name: 
                        contract_name = "Unknown_Contract"
                else:
                    # 如果结果是字符串（通常是报错信息）
                    error_msg = result_data if isinstance(result_data, str) else "Empty result"
                    print(f"[!] Warning: Failed to get contract name. API returned: {error_msg}")
                    contract_name = "Unknown_Contract"

            except Exception as e:
                print(f"[!] HTTP Request Failed: {e}")
                contract_name = "Unknown_Contract"

            print("[i]Contract name: {contract_name}".format(contract_name=contract_name))

            self.refactor_file_structure(self.contract_address, contract_name)
            CONTRACT_CACHE[self.contract_address] = contract_name

            return contract_name

    def detect_and_switch_solc_version(self) -> None:
        target = os.path.join("tmp",self.contract_address,self.contract_name+".sol")
        solc_versions = []
        with open(target, encoding= "utf8") as file_desc:
            buf = file_desc.read()
            solc_versions = PATTERN.findall(buf)
        if not solc_versions:
            print("[!]No solc version found. Manual switching is required")
            exit()
        solc_version = solc_versions[0]
        # Current version is the same as the required version
        if solc_version == solc_select.current_version()[0]:
            pass
        # Switch to the required version (including installation if necessary)
        else:
            solc_select.switch_global_version(version=solc_version, always_install=True)
        # Check if the version is switched successfully
        if solc_select.current_version()[0] != solc_version:
            print("[!]Failed to switch to the required solc version")
            exit()
        else:
            print("[+]Using solc version: {}".format(solc_version))

    def download_contracts(self, contract_address: str, platform: str) -> None:
        if self.contract_address in CONTRACT_CACHE:
            return 
            
        # 1. 确定 Slither 认可的网络名称
        slither_platform = SUPPORTED_NETWORK[platform]["name"]
        if platform == "ethereum" or slither_platform == "ethereum":
            slither_platform = "mainnet"
        
        # 2. 构造命令 (使用修正后的 slither_platform)
        command = "slither-flat {platform}:{address} --strategy OneFile {key_command} {api_key}".format(
            platform=slither_platform, # 使用 mainnet
            address=contract_address,
            key_command=SUPPORTED_NETWORK[platform]["key_command"],
            api_key=SUPPORTED_NETWORK[platform]["api_key"])
            
        print(f"[DEBUG] Executing: {command}") # 打印一下确保万无一失
        os.system(command)
        print("[*]Downloaded contracts successfully")

    def refactor_file_structure(self, contract_address: str, contract_name: str) -> None:
        # Original structure: crytic-export/flattening/*.sol
        # New structure: address/*.sol
        if not os.path.exists(os.path.join("tmp", contract_address)):
            os.mkdir(os.path.join("tmp", contract_address))
        
        if os.path.exists("crytic-export/flattening"):
            for contract_file in os.listdir("crytic-export/flattening"):
                shutil.move(os.path.join("crytic-export/flattening", contract_file), os.path.join("tmp", contract_address, contract_name+".sol"))
        else:
            print("[!]Cannot find the flattened contract files")
            shutil.rmtree(os.path.join("tmp", contract_address))
        try:
            shutil.rmtree("crytic-export")
            print("[*]Refactor the file structure successfully")
        except:
            print("[!]Failed to refactor the file structure")

    def get_contracts(self) -> Tuple[Optional[Contract], Optional[Slither]]:
        if not os.path.exists(os.path.join("tmp",self.contract_address)) or not os.path.exists(os.path.join("tmp",self.contract_address,self.contract_name+".sol")):
            print("[!]Contract {address}:{contract_name} not found: contract is not downloaded successfully.".format(address=self.contract_address, contract_name=self.contract_name))
            return (None, None)
        
        self.detect_and_switch_solc_version()
        
        curr_dir = os.getcwd()
        os.chdir(os.path.join("tmp",self.contract_address))
        slither = Slither(self.contract_name+".sol")
        os.chdir(curr_dir)
        
        try:
            contracts = slither.get_contract_from_name(self.contract_name)
            contract = contracts[0]
            return (contract, slither)
        except:
            print("[!]Contract not found: the contract name is not the same as its file name or contract is not downloaded successfully.")
            return (None, None)

    def filter_out_nonExistent_functions(self, functions: List[str]) -> Tuple[List[str], List[str]]:
        functions_in_contract = set(function.name for function in self.contract.functions)
        functions_exist = list(set(functions).intersection(functions_in_contract))
        functions_not_exist = list(set(functions).difference(functions_exist))
        return (functions_exist, functions_not_exist)

    # def extract_single_function(
    #         contract: Contract, 
    #         contract_file_path: str, 
    #         function_name: str, 
    #         file_handler: TextIOWrapper
    #         ):
    #     print("[+]Extracting {function} from {contract}".format(function=function_name, contract=contract.name))
    #     stack = []
    #     flag = False
    #     isExist = check_if_function_exists(contract=contract, function_name=function_name)
    #     if isExist:
    #         with open(contract_file_path, "r") as file:
    #             lines = file.readlines()
    #             for line in lines:
    #                 if not flag:
    #                     if ("function " + function_name in line) and (";" not in line):
    #                         # Filter out the function declaration from the interface
    #                         flag = True
    #                 else: 
    #                     pass
    #                 if flag:
    #                     file_handler.write(line)
    #                     if "{" in line:
    #                         stack.append("{")
    #                     if "}" in line:
    #                         stack.pop()
    #                         if not stack:
    #                             flag = False
    #     else:
    #         print("[!]{function} not found in {contract}".format(
    #             function=function_name, 
    #             contract=contract.name))

    def extract_functions(self, functions: List[str]) -> str:
        # @todo Cannot distinguish the functions with the same name: if there are two functions with the same name (one in the library, one in the contract), all code snippet of them will be extracted
        code_snippet = ""
        stack = []
        flag = False
        buf = ""
        isFunction = False
        with open(self.contract_file_path, "r") as file:
            lines = file.readlines()
            for line in lines:
                if not flag:
                    if [function for function in functions if "function " + function in line]:
                        flag = True          
                if flag:
                    # Check if the function declaration is in the interface (; before {)
                    if (not isFunction and (";" in line)):
                        buf = "" # Clear the buffer
                        flag = False
                        continue
                    buf += line
                    if "{" in line:
                        stack.append("{")
                        isFunction = True
                    if "}" in line:
                        stack.pop()
                        if not stack:
                            code_snippet += buf
                            buf = ""
                            flag = False
                            isFunction = False
        print("[*]Extracted successfully")
        return code_snippet

    def extract_functions_from_single_contract(self) -> str:
        # @note some Ethereum functions could not be extracted, e.g., address.balance()
        # called_functions = []
        # get the function object
        if not self.contract:
            return ""
        
        signature = ""
        for function in self.contract.functions:
            if self.entry_point in function.solidity_signature:
                signature = function.solidity_signature
                break
        if signature == "":
            print("[!]{entry_point} not found in {contract}".format(entry_point=self.entry_point, contract=self.contract.name))
            return
        function_object = self.contract.get_function_from_signature(signature)
        # --- 修复 Slither 新版本 HighLevelCall 兼容性 (开始) ---
        all_high_level_calls = function_object.all_high_level_calls()
        filtered_calls = []
        
        for call in all_high_level_calls:
            # 1. 尝试从新版 Slither 对象中提取
            if hasattr(call, 'destination') and hasattr(call, 'function'):
                contract = call.destination
                function = call.function
            # 2. 尝试从旧版元组中提取
            elif isinstance(call, (list, tuple)) and len(call) == 2:
                contract, function = call
            else:
                continue # 无法识别的格式，跳过

            # 过滤无效合约或函数
            if not contract or not function:
                continue
            
            # 过滤标准库合约
            if hasattr(contract, 'name') and contract.name.lower() in [s.lower() for s in STANDARD_CONTRACTS]: 
                continue
            
            # 确保 function 有 name 属性（防止后续报错）
            if not hasattr(function, 'name'):
                continue

            filtered_calls.append((contract, function))
        # --- 修复 Slither 新版本 HighLevelCall 兼容性 (结束) ---
        # all_calls = function_object.all_internal_calls()
        
        # --- 修复 Slither 新版本兼容性问题 (开始) ---
        # 新版 Slither 会返回一些没有 .name 属性的对象(如 SolidityCall)，必须过滤掉
        all_internal_calls = [
            call.name for call in function_object.all_internal_calls() 
            if hasattr(call, 'name')
        ]
        all_solidity_calls = [
            call.name for call in function_object.all_solidity_calls() 
            if hasattr(call, 'name')
        ]
        # --- 修复 Slither 新版本兼容性问题 (结束) ---

        filtered_internal_calls = list(set(all_internal_calls).difference(set(all_solidity_calls)))
        #@debug-start
        # print("[*]All internal calls:", [function.name for function in function_object.all_internal_calls()])
        # print("[*]All low level calls:", [function[0].name for function in function_object.all_low_level_calls()])
        # print("[*]All high level calls:", [(function[0].name, function[1].name) for function in function_object.all_high_level_calls()])
        # print("[*]All library calls:", [(function[0].name, function[1].name) for function in function_object.all_library_calls()])
        # print("[*]All solidity calls:", [function.name for function in function_object.all_solidity_calls()])
        #@debug-end
        # filter out the modifiers and the functions in the modifiers
        # for function in all_calls:
        #     if function.name not in self.filtered_functions \
        #     and "abi." not in function.name \
        #     and "require(" not in function.name \
        #     and "revert(" not in function.name \
        #     and "assert(" not in function.name \
        #     and "keccak256(" not in function.name:
        #         called_functions.append(function.name)
        print("[+]Internal subcalls of {function} in {contract}: {called_func}".format(
            function=self.entry_point, 
            contract=self.contract.name,
            called_func=list(set([(contract.name, function.name) for (contract, function) in filtered_calls]).union(set([(self.contract_name, internal_call) for internal_call in filtered_internal_calls])))))
        
        # extract the target functions
        all_calls = list(set([function.name for (_, function) in filtered_calls]).union(set(filtered_internal_calls)))
        target_functions = [self.entry_point] + all_calls
        (functions_exist, functions_not_exist) = self.filter_out_nonExistent_functions(functions=target_functions)
        if not functions_exist:
            print("[!]{functions} could not be found in {contract}".format(functions=target_functions, contract=self.contract.name))
            return
        if functions_not_exist:
            print("[!]{functions} could not be found in {contract}".format(functions=functions_not_exist, contract=self.contract.name))
        
        print("[+]Extracting {functions} from {contract}".format(functions=functions_exist, contract=self.contract.name))
        return self.extract_functions(functions=functions_exist)
        # for function in [function_name] + called_functions:
        #     extract_single_function(
        #         contract=contract, 
        #         contract_file_path=contract_file_path, 
        #         function_name=function, 
        #         file_handler=file_handler
        #         )

    # def extract_functions_from_contracts(
    #         contracts: List[Contract],
    #         contract_file_path: str, 
    #         entry_point: str, 
    #         filtered_functions: List[str], 
    #         file_handler: TextIOWrapper
    #         ):
    #     for contract in contracts:
    #         # Ignore interface
    #         if contract.is_interface:
    #             continue
    #         if entry_point in [f.name for f in contract.functions]:
    #             print("[+]Processing {contract}".format(contract=contract.name))
    #             extract_functions_from_single_contract(
    #                 contract=contract, 
    #                 contract_file_path=contract_file_path, 
    #                 function_name=entry_point, 
    #                 filtered_functions=filtered_functions, 
    #                 file_handler=file_handler
    #                 )

    # filter out the functions from openzeppelin contracts, abi, require, revert, assert, keccak256
    # @todo could have a white list of openzeppelin contracts' functions and replace this function
    def filter_modifiers_functions(self) -> List[str]:
        if not self.contract:
            return []
        filtered_functions = []
        inheritance = self.contract.inheritance
        for inherited_contract in inheritance:
            if inherited_contract.name in WHITE_LIST:
                for function in inherited_contract.functions:
                    filtered_functions.append(function.name)
        filtered_functions += [m.name for m in self.contract.modifiers]
        return filtered_functions
    
    # @debug
    def debug_log(self) -> None:
        print("*" * 150)
        print("Contract Address: ", self.contract_address)
        print("Contract Name: ", self.contract_name)
        print("Entry Point: ", self.entry_point)

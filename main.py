import sys
import os
sys.path.insert(0, os.getcwd()) # <--- 强制 Python 优先从当前目录查找文件
import time
import shutil
import argparse
import jsonlines
from itertools import combinations

# [修改] 移除了 torch 引用，防止加载冲突
# import torch 

from utils.transaction import Transaction
from utils.detector import Detector
from utils.log import attack_log
from utils.debug_log import *
from utils.tranxToUserCalls import extract_userCalls_from_tranx
from utils.checkFlashloan import flagFlashloan
from utils.matchRelatedActions import matchRelatedActions
# [修改] 只保留 API 模式需要的 multi_thread
from utils.multiThreadHelper import multi_thread
from utils.fast_filter import fast_filter
# from utils.load_model import load_model_for_device # [修改] 不需要本地模型加载器

# run with command: python main.py -tx txhash -bp platform
parser = argparse.ArgumentParser()
parser.add_argument("-tx",
                    "--transaction_hash",
                    help="The hash of the transation",
                    action="store", 
                    dest="txhash", 
                    type=str)
parser.add_argument("-bp",
                    "--blockchain_platform",
                    help="The blockchain platform where the test contract is deployed",
                    action="store", 
                    dest="platform", 
                    type=str)
parser.add_argument("--debug",
                    action='store_const',
                    const=True,
                    default=False,
                    help="Enable debug mode",
                    dest="debug_mode")

# [修改] 移除了 use_local_model 和 model_path 参数
# 因为现在强制使用 API 模式，不需要加载本地模型文件

args = parser.parse_args()

txhash = args.txhash
platform = args.platform
debug_mode = args.debug_mode

start_time = time.time()
result = ""

if fast_filter(tx=txhash, chain=platform):
    result = "False"
else:
    # Initialization
    if os.path.exists("tmp"):
        shutil.rmtree("tmp")
    os.makedirs("tmp")

    # Detection
    try:
        transaction = Transaction(txhash=txhash, platform=platform)
        userAccount = transaction.user_account
        userCalls = extract_userCalls_from_tranx(userAccount=userAccount, 
                                                                decoded_transaction=transaction.decoded_transaction, 
                                                                chain=transaction.platform)
        matchRelatedActions(userCalls=userCalls)

        flagFlashloan(userCalls=userCalls, userAccount=userAccount)

        old_global_token_balance = dict()
        for userCall in userCalls:
            userCall.update_contract_address_name_mapping(platform=platform)
            userCall.global_token_balance_change = old_global_token_balance.copy()
            old_global_token_balance = userCall.update_gloabl_token_balance_change()

        # [修改] 核心推理部分
        # 直接使用多线程调用 API，不加载本地模型
        # multi_thread 内部会初始化 PriceChangeInferenceUnit
        # 由于我们修改了 PriceChangeInferenceUnit，它会默认使用 API
        multi_thread(userCalls)

        filtered_userCalls = [userCall 
                            for userCall in userCalls 
                            if userCall.userCallPurpose or any(userCall.priceChangeInference.values())]
        
        # Print debug information
        if debug_mode:
            print("#" * 150)
            print("Processed UserCall Details:")
            for userCall in filtered_userCalls:
                log_defiPurpose_sequence(userCall)
                log_defiAction(userCall)
                log_price_calculation_functions(userCall)
                log_functions(userCall)
                log_transfer_details(userCall)
                log_flashloan(userCall)
                log_relatedAction(userCall)
                log_priceChangeTendency(userCall)
            print("Detect Result:")
        
        attack_detected = False
        if len(filtered_userCalls) >= 3:
            for userCall_Combination in combinations(filtered_userCalls, 3):
                detector = Detector(userCalls=list(userCall_Combination), userAccount=userAccount)
                for detect_result in detector.results:
                    if detect_result.isAttack:
                        attack_detected = True
                        if debug_mode:
                            attack_log(detect_result)

        if not attack_detected:
            print("[*]The transaction is a price manipulation attack: False")
            result = "False"
        else:
            print("[*]The transaction is a price manipulation attack: True")
            result = "True"

    except Exception as e:
        import traceback
        print("\n❌ [程序崩溃] 详细报错信息如下：")
        print("="*50)
        traceback.print_exc()
        print("="*50)
        
        result = "Error"

end_time = time.time()
print("[*]Execution Time: ", end_time - start_time, "s")

# Record detection result
print("Write detection result to 'detection_result.jsonl'")
with jsonlines.open("detection_result.jsonl", 'a') as f:
    if result == "True":
        f.write({txhash: "True", "time": end_time - start_time})
    elif result == "False":
        f.write({txhash: "False", "time": end_time - start_time})
    else:
        f.write({txhash: "Error", "time": end_time - start_time})

# Clean up
if os.path.exists("tmp"):
    shutil.rmtree("tmp")
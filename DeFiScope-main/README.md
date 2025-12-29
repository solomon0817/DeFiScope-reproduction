# DeFiScope 复现 (API Version)

本项目是论文 **"Detecting Various DeFi Price Manipulations with LLM Reasoning" (ASE 2025)** 复现。

---

## 🛠️ 安装与环境配置 (Installation)

### 1. 克隆仓库
下载本项目代码到本地：

```bash
git clone <你的仓库地址>
cd DeFiScope-Reproduction
```

### 2. 创建虚拟环境 (推荐 Conda)
为了避免依赖冲突，建议创建一个新的 Python 3.10 环境：

```bash
# 创建名为 defiscope 的环境，指定 Python 3.10
conda create -n defiscope python=3.10 -y

# 激活环境
conda activate defiscope
```

### 3. 安装依赖
安装项目所需的 Python 库：

```bash
pip install -r requirements.txt
```

> **⚠️ 常见报错解决 (Solidity 编译器)**
> 本项目依赖 `slither-analyzer` 进行静态分析。如果运行报错提示找不到 `solc`，请执行以下命令安装版本管理器并设置版本：
> ```bash
> pip install solc-select
> solc-select install 0.8.0
> solc-select use 0.8.0
> ```

---

## ⚙️ 配置 (Configuration)

由于本项目使用 OpenAI 模型（如 GPT-4o）进行推理，运行前必须配置 API Key。

**Linux / macOS:**
```bash
export OPENAI_API_KEY='sk-your-api-key-here'
```

**Windows (PowerShell):**
```powershell
$env:OPENAI_API_KEY='sk-your-api-key-here'
```

---

## 🚀 运行检测 (Usage)

使用 `main.py` 脚本对特定交易进行检测。

### 命令格式
```bash
python main.py -tx <交易哈希> -bp <链ID>
```

* **`-tx`**: 待检测的交易哈希 (Transaction Hash)
* **`-bp`**: 区块链平台 (Blockchain Platform)，支持 `ethereum` 或 `bsc`

### 运行示例
检测一笔 Ethereum 上的交易：

```bash
python main.py -tx 0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef -bp ethereum
```

### 查看结果
运行结束后，检测结果（包含 LLM 的推理分析、攻击判定等）将写入当前目录下的文件：
* 📄 **`detection_result.jsonl`**

---

## 📂 数据集说明 (Dataset)

`dataset/` 目录包含论文原始评估数据，可用于测试复现效果：
* **`D1.csv`, `D2.csv`, `D3.csv`**: 论文 §VII 中的主要评估数据集。
* **`1000_tx.csv`**: 包含 1000 笔用于对比分析的交易数据。

---

## ✏️ 引用 (Citation)

如果您使用了本项目的代码或逻辑，请引用原始论文：

```bibtex
@inproceedings{zhong2025defiscope,
      title={{Detecting Various DeFi Price Manipulations with LLM Reasoning}}, 
      author={Zhong, Juantao and Wu, Daoyuan and Liu, Ye and Xie, Maoyi and Liu, Yang and Li, Yi and Liu, Ning},
      booktitle={Proc. IEEE/ACM Automated Software Engineering (ASE)},
      year={2025}
}
```
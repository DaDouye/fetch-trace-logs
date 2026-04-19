# RAG系统配置文件

# Hugging Face API Token (可选，如果使用在线模型)
# 请在使用前设置 HUGGINGFACEHUB_API_TOKEN 环境变量
HUGGINGFACEHUB_API_TOKEN = ""

# 嵌入模型配置
EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

# 本地LLM模型配置（可选）
LOCAL_LLM_MODEL_PATH = None  # 如果使用本地模型，请指定路径

# 向量数据库配置
VECTOR_DB_PATH = "./vector_store_index"

# 文本分割配置
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200

# 检索配置
SEARCH_K = 5  # 检索相似文档的数量

# 日志级别
LOG_LEVEL = "INFO"
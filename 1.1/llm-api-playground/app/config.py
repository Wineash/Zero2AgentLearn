import os
from dotenv import load_dotenv

# 加载项目根目录下的 .env 文件
# 因为 config.py 在 app/ 里，需要回到上层目录
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(dotenv_path)

# 读取 API Key，如果没有设置则抛出异常或给默认提示
API_KEY = os.getenv("API_KEY")
if not API_KEY:
    raise ValueError("请在 .env 文件中设置 API_KEY")
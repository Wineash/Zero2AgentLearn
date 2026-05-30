from app.config import API_KEY

def main():
    print(f"成功读取到 API Key: {API_KEY[:8]}...（已隐藏后续部分）")
    # 在这里调用 LLM API，使用 API_KEY
    # 例如: openai.api_key = API_KEY

if __name__ == "__main__":
    main()
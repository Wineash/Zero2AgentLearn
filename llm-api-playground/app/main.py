import os
import re

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

from app.llm_client import OpenAICompatibleClient
from app.prompts import AGENT_SYSTEM_PROMPT
from app.tools import available_tools


def main():
    """
    本 demo 使用 ReAct（Reasoning + Acting）模式让 LLM 自主调用工具完成任务。

    核心思想：
    - 每次循环，把"历史记录（prompt_history）"拼接成一个大段文本发给 LLM
    - LLM 返回一个 "Thought: ... Action: ..." 的结构化回复
    - 解析出 Action，执行对应的工具函数，得到结果
    - 将结果以 "Observation: ..." 追加到历史中，进入下一轮循环
    - 直到 LLM 输出 Action: Finish[...] 表示任务完成，或者超过最大循环次数

    历史记录示意（prompt_history 列表中的逐条内容）：
      用户请求: 帮我查天气并推荐景点
      Thought: 先查天气
      Action: get_weather(city="北京")
      Observation: 北京当前天气: Clear，气温27摄氏度
      Thought: 天气不错，推荐景点
      Action: Finish[推荐你去故宫...]
    """

    # ============================================================
    # 1. 从环境变量读取配置，初始化 LLM 客户端
    # ============================================================
    API_KEY = os.environ.get("API_KEY")
    BASE_URL = os.environ.get("BASE_URL")
    MODEL_ID = os.environ.get("MODEL_ID")

    llm = OpenAICompatibleClient(
        model=MODEL_ID,
        api_key=API_KEY,
        base_url=BASE_URL
    )

    # ============================================================
    # 2. 初始化对话历史
    # ============================================================
    # prompt_history 是整个对话的"记忆"：
    # - 它是一个字符串列表，每条是对话的一个回合
    # - 每轮循环都会把整个列表用换行符拼成一个 big prompt 发给 LLM
    # - LLM 因此能"记住"之前发生了什么（查了什么、工具返回了什么）
    user_prompt = "你好，请帮我查询一下今天北京的天气，然后根据天气推荐一个合适的旅游景点。"
    prompt_history = [f"用户请求: {user_prompt}"]

    print(f"用户输入: {user_prompt}\n" + "=" * 40)

    # ============================================================
    # 3. ReAct 主循环
    # ============================================================
    # 最多循环 5 次，防止 LLM 陷入死循环或反复调用失败的工具
    for i in range(5):
        print(f"--- 循环 {i + 1} ---\n")

        # --------------------------------------------------------
        # 3.1 拼接完整 Prompt，调用 LLM
        # --------------------------------------------------------
        # 把"用户请求 → Thought/Action → Observation → Thought/Action → ..."
        # 这一整串历史全部拼在一起，作为当次的输入
        full_prompt = "\n".join(prompt_history)

        # 调用 LLM，期望它按 AGENT_SYSTEM_PROMPT 规定的格式回复
        llm_output = llm.generate(full_prompt, system_prompt=AGENT_SYSTEM_PROMPT)

        # ---- 截断多余输出 ----
        # LLM 有时会在一次回复中输出多组 Thought-Action 对，例如：
        #   Thought: 查天气
        #   Action: get_weather(...)
        #   Thought: 天气拿到了，查景点    ← 多余的第二个 Thought-Action
        #   Action: get_attraction(...)
        # 我们只取第一组，后面的裁掉，保证每轮循环只执行一个动作
        match = re.search(
            r'(Thought:.*?Action:.*?)(?=\n\s*(?:Thought:|Action:|Observation:)|\Z)',
            llm_output, re.DOTALL
        )
        if match:
            truncated = match.group(1).strip()
            if truncated != llm_output.strip():
                llm_output = truncated
                print("已截断多余的 Thought-Action 对")

        print(f"模型输出:\n{llm_output}\n")
        # 把 LLM 的回复记录到历史中，下一轮 LLM 就能看到自己说过什么
        prompt_history.append(llm_output)

        # --------------------------------------------------------
        # 3.2 从 LLM 回复中解析出 Action
        # --------------------------------------------------------
        # Action 行示例：
        #   Action: get_weather(city="北京")
        #   Action: get_attraction(city="北京", weather="Clear")
        #   Action: Finish[今天北京天气很好，推荐去故宫]
        action_match = re.search(r"Action: (.*)", llm_output, re.DOTALL)

        # 如果 LLM 没按格式输出 Action，给它一个错误反馈，让它在下一轮纠正
        if not action_match:
            observation = "错误: 未能解析到 Action 字段。请确保你的回复严格遵循 'Thought: ... Action: ...' 的格式。"
            observation_str = f"Observation: {observation}"
            print(f"{observation_str}\n" + "=" * 40)
            prompt_history.append(observation_str)
            continue  # 跳过本轮剩余逻辑，进入下一轮循环

        action_str = action_match.group(1).strip()

        # --------------------------------------------------------
        # 3.3 处理 Finish 动作 —— 任务完成，退出循环
        # --------------------------------------------------------
        if action_str.startswith("Finish"):
            # Finish[...] 中方括号内的内容就是 LLM 给用户的最终答案
            final_answer = re.match(r"Finish\[(.*)\]", action_str).group(1)
            print(f"任务完成，最终答案: {final_answer}")
            break  # 退出 for 循环，程序结束

        # --------------------------------------------------------
        # 3.4 解析工具名和参数，执行工具调用
        # --------------------------------------------------------
        # 从 "get_weather(city=\"北京\")" 中提取：
        #   tool_name = "get_weather"
        #   kwargs    = {"city": "北京"}
        tool_name = re.search(r"(\w+)\(", action_str).group(1)
        args_str = re.search(r"\((.*)\)", action_str).group(1)
        kwargs = dict(re.findall(r'(\w+)="([^"]*)"', args_str))

        # 查表调用对应的 Python 函数
        if tool_name in available_tools:
            observation = available_tools[tool_name](**kwargs)
        else:
            observation = f"错误:未定义的工具 '{tool_name}'"

        # --------------------------------------------------------
        # 3.5 将工具执行结果以 Observation 格式记录到历史
        # --------------------------------------------------------
        observation_str = f"Observation: {observation}"
        print(f"{observation_str}\n" + "=" * 40)
        prompt_history.append(observation_str)
        # 本轮结束，回到 for 循环开头，LLM 会在下一轮看到 Observation 后继续思考


if __name__ == "__main__":
    main()

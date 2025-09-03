import json
import os
import time
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from langchain.schema import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pathlib import Path
import threading
from tqdm import tqdm
import datetime

# 创建一个锁对象，用于保护共享资源
json_lock = threading.Lock()

def load_pr_data(json_file: str) -> List[Dict]:
    """
    从JSON文件中加载PR数据
    
    Args:
        json_file: PR数据文件路径
        
    Returns:
        PR数据列表
    """
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            pr_data = json.load(f)
        
        # 添加统计信息：已分析和未分析的PR数量
        analyzed_count = sum(1 for pr in pr_data if 'isLogicError' in pr)
        print(f"成功加载 {len(pr_data)} 个PR数据，其中 {analyzed_count} 个已有分析结果，{len(pr_data) - analyzed_count} 个待分析")
        return pr_data
    except Exception as e:
        print(f"加载PR数据失败: {str(e)}")
        return []

def save_pr_data(json_file: str, pr_data: List[Dict]):
    """
    保存更新后的PR数据到JSON文件
    
    Args:
        json_file: 目标文件路径
        pr_data: 更新后的PR数据列表
    """
    try:
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(pr_data, f, ensure_ascii=False, indent=2)
        print(f"成功保存 {len(pr_data)} 个PR数据到 {json_file}")
    except Exception as e:
        print(f"保存PR数据失败: {str(e)}")

def update_pr_in_file(json_file: str, pr_number: int, is_logic_error: bool, error_description: str):
    """
    在原始文件中更新单个PR的逻辑错误分析结果
    
    Args:
        json_file: JSON文件路径
        pr_number: PR编号
        is_logic_error: 是否是逻辑错误
        error_description: 错误描述
    """
    with json_lock:
        try:
            # 读取整个文件
            with open(json_file, 'r', encoding='utf-8') as f:
                pr_data = json.load(f)
                
            # 更新指定PR
            for pr in pr_data:
                if pr.get('number') == pr_number:
                    pr['isLogicError'] = is_logic_error
                    pr['logicErrorDescription'] = error_description
                    break
                    
            # 写回文件
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(pr_data, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            print(f"更新PR #{pr_number}数据失败: {str(e)}")

def analyze_pr_logic_error(llm: ChatOpenAI, pr_data: Dict) -> Optional[Dict]:
    """
    使用LLM分析PR是否修复了逻辑漏洞
    
    Args:
        llm: LLM实例
        pr_data: PR数据
        
    Returns:
        分析结果，包含isLogicError和description字段
    """
    # 提取PR的标题和对话内容
    title = pr_data.get('title', '')
    pr_number = pr_data.get('number', 'Unknown')
    
    # 获取conversation数据
    conversation = pr_data.get('conversation', {})
    author = conversation.get('author', '')
    body = conversation.get('body', '')
    issue_comments = conversation.get('issue_comments', [])
    review_comments = conversation.get('review_comments', [])
    reviews = conversation.get('reviews', [])
    
    # 系统消息定义分析要求
    system_message = SystemMessage(content="""
    You are an expert code analyzer specializing in identifying logic errors in software systems. Your task is to determine whether the issue discussed in the conversation is a logical error.

    **Definition of Logic Error:** 
    A logic error is a bug in a program that causes it to operate incorrectly but not terminate abnormally (or crash). Logic errors occur in both compiled and interpreted languages. A logic error produces unintended or undesired output or behavior. Examples include:
    - Incorrect conditional statements
    - Improper state transitions
    - Race conditions
    - Boundary condition errors
    - Improper error handling
    - Incorrect algorithm implementation
    - Timing or synchronization issues
    - Data flow problems

    **Input:**
    - PR title
    - PR description (body)
    - Comments and reviews on the PR

    **Output requirements:**
    Provide your analysis in JSON format with the following structure:
    ```
    {
        "isLogicError": true/false,
        "confidence": "high/medium/low",
        "description": "Brief explanation of your reasoning (2-3 sentences)"
    }
    ```

    **Analysis Guidelines:**
    1. Focus on code logic problems, not syntax errors, typos, or style issues
    2. Look for words like "fix", "bug", "issue", "incorrect behavior", "wrong logic"
    3. Check if the PR addresses inconsistent program state or incorrect behavior
    4. Consider the PR title, description, and any technical discussions in comments
    5. Look for indications that the code previously produced unexpected results
    """)

    # 构建prompt
    formatted_comments = []
    for comment in issue_comments:
        formatted_comments.append(f"- {comment.get('author', '')}: {comment.get('body', '')}")
    
    formatted_reviews = []
    for review in reviews:
        if review.get('body'):
            formatted_reviews.append(f"- {review.get('author', '')}: {review.get('body', '')}")
    
    prompt = f"""
    Please analyze this Pull Request to determine if it fixes a logic error:

    ## PR Information
    - PR Number: {pr_number}
    - Title: {title}
    - Author: {author}
    
    ## PR Description
    {body}
    
    ## Comments
    {chr(10).join(formatted_comments)}
    
    ## Reviews
    {chr(10).join(formatted_reviews)}
    
    Based on this information, is this PR fixing a logic error in the code? Provide your analysis in the required JSON format.
    """

    messages = [
        system_message,
        HumanMessage(content=prompt)
    ]

    try:
        response = llm.invoke(messages)
        response_content = response.content.strip()
        
        # 从回复中提取JSON部分
        json_start = response_content.find('{')
        json_end = response_content.rfind('}') + 1
        if json_start != -1 and json_end != -1:
            json_str = response_content[json_start:json_end]
            result = json.loads(json_str)
            return result
        else:
            print(f"无法从响应中提取JSON: {response_content}")
            return None
    except Exception as e:
        print(f"分析PR #{pr_number} 时出错: {str(e)}")
        return None

def process_pr_batch(pr_batch: List[Dict], json_file: str, thread_id: int):
    """
    处理一批PR
    
    Args:
        pr_batch: 要处理的PR列表
        json_file: 原始JSON文件路径
        thread_id: 线程ID
    """
    # 初始化LLM
    try:
        llm = ChatOpenAI(
            model="gpt-5-mini-2025-08-07",  # 可以根据需要选择合适的模型
            api_key=os.getenv('OPENAI_API_KEY')
        )
    except Exception as e:
        print(f"线程 {thread_id} 初始化LLM失败: {str(e)}")
        return
    
    print(f"线程 {thread_id} 开始处理 {len(pr_batch)} 个PR")
    
    for pr in tqdm(pr_batch, desc=f"线程 {thread_id}"):
        # 检查PR是否已有逻辑错误分析
        if 'isLogicError' in pr:
            print(f"PR #{pr.get('number')} 已有分析结果，跳过")
            continue
        
        # 使用LLM分析PR
        analysis_result = analyze_pr_logic_error(llm, pr)
        
        if analysis_result:
            is_logic_error = analysis_result.get('isLogicError', False)
            description = analysis_result.get('description', '')
            confidence = analysis_result.get('confidence', 'low')
            
            print(f"PR #{pr.get('number')} 分析结果: isLogicError={is_logic_error}, confidence={confidence}")
            
            # 更新PR数据
            update_pr_in_file(json_file, pr.get('number'), is_logic_error, description)
            
            # 添加延迟避免API限制
            time.sleep(1)
        else:
            print(f"PR #{pr.get('number')} 分析失败")
            
    print(f"线程 {thread_id} 完成处理")

def analyze_prs_with_threads(json_file: str, num_threads: int = 4):
    """
    使用多线程分析PR
    
    Args:
        json_file: PR数据文件路径
        num_threads: 线程数量
    """
    # 加载PR数据
    pr_data = load_pr_data(json_file)
    if not pr_data:
        return
    
    # 过滤掉已有分析结果的PR
    prs_to_analyze = [pr for pr in pr_data if 'isLogicError' not in pr]
    
    # 添加详细统计信息
    skipped_prs = len(pr_data) - len(prs_to_analyze)
    print(f"从 {len(pr_data)} 个PR中筛选出 {len(prs_to_analyze)} 个需要分析的PR，跳过 {skipped_prs} 个已有分析结果的PR")
    
    # 打印一些被跳过的PR信息作为示例
    if skipped_prs > 0:
        skipped_examples = [pr.get('number') for pr in pr_data if 'isLogicError' in pr][:5]
        if skipped_examples:
            print(f"被跳过的PR示例: {', '.join(map(str, skipped_examples))} ...")
    
    if not prs_to_analyze:
        print("没有需要分析的PR，任务完成")
        return
    
    # 将PR分成多个批次
    batch_size = len(prs_to_analyze) // num_threads
    if batch_size == 0:
        batch_size = 1
    
    pr_batches = []
    for i in range(0, len(prs_to_analyze), batch_size):
        end_idx = min(i + batch_size, len(prs_to_analyze))
        pr_batches.append(prs_to_analyze[i:end_idx])
    
    print(f"将 {len(prs_to_analyze)} 个PR分成 {len(pr_batches)} 个批次进行处理")
    
    # 使用线程池处理PR
    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = []
        for i, batch in enumerate(pr_batches):
            future = executor.submit(process_pr_batch, batch, json_file, i+1)
            futures.append(future)
        
        # 等待所有线程完成
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                print(f"线程执行出错: {str(e)}")
    
    print("所有PR分析完成")

def main():
    # 记录开始时间
    start_time = time.time()
    
    # PR数据文件路径
    json_file = "px4_navigator_prs.json"
    
    # 检查环境变量
    if not os.getenv('OPENAI_API_KEY'):
        print("错误: 未设置OPENAI_API_KEY环境变量")
        return
    
    # 使用多线程分析PR
    analyze_prs_with_threads(json_file, num_threads=4)
    
    # 记录结束时间并计算总耗时
    end_time = time.time()
    elapsed_time = end_time - start_time
    hours, remainder = divmod(elapsed_time, 3600)
    minutes, seconds = divmod(remainder, 60)

    print(f"总耗时: {int(hours)}小时 {int(minutes)}分钟 {seconds:.2f}秒")

if __name__ == "__main__":
    main()

import requests
import json
import time
import os
from datetime import datetime
import threading
from tqdm import tqdm
import datetime

# 创建一个锁对象，用于保护JSON文件的读写
json_lock = threading.Lock()

def load_pr_data(json_file="px4_navigator_prs.json"):
    """
    从JSON文件加载PR数据
    
    Args:
        json_file: PR数据文件路径
        
    Returns:
        list: PR数据列表
    """
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            pr_data = json.load(f)
        
        # 计算已有对话和缺少对话的PR数量
        with_conversation = sum(1 for pr in pr_data if 'conversation' in pr)
        without_conversation = len(pr_data) - with_conversation
        
        print(f"成功加载 {len(pr_data)} 个PR数据")
        print(f"其中 {with_conversation} 个已有对话数据，{without_conversation} 个缺少对话数据")
        
        return pr_data
    except Exception as e:
        print(f"加载PR数据失败: {str(e)}")
        return []

def save_pr_data(pr_data, json_file="px4_navigator_prs.json"):
    """
    保存更新后的PR数据
    
    Args:
        pr_data: 更新后的PR数据列表
        json_file: 目标文件路径
    """
    with json_lock:
        try:
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(pr_data, f, ensure_ascii=False, indent=2)
            print(f"成功保存 {len(pr_data)} 个PR数据到 {json_file}")
        except Exception as e:
            print(f"保存PR数据失败: {str(e)}")

def get_pr_conversation(pr_number, headers, session=None):
    """
    获取PR的对话内容
    
    Args:
        pr_number: PR编号
        headers: GitHub API的请求头
        session: 请求会话（可选）
        
    Returns:
        dict: 包含PR对话内容的字典，如果获取失败则返回None
    """
    owner = "PX4"
    repo = "PX4-Autopilot"
    
    if session is None:
        session = requests.Session()
    
    api_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
    
    try:
        # 获取PR基本信息
        print(f"正在获取PR {pr_number} 的信息...")
        response = session.get(api_url, headers=headers)
        
        # 检查API限制
        if response.status_code == 403:
            rate_limit = response.headers.get('X-RateLimit-Remaining', 'unknown')
            reset_time = response.headers.get('X-RateLimit-Reset', 0)
            if reset_time:
                reset_time = datetime.datetime.fromtimestamp(int(reset_time))
                print(f"API速率限制: 剩余请求数 {rate_limit}, 重置时间 {reset_time}")
            return None
            
        if response.status_code != 200:
            print(f"获取PR信息失败，状态码: {response.status_code}")
            print(f"错误信息: {response.text}")
            return None
        
        pr_data = response.json()
        
        # 获取PR评论（issue comments）
        comments_url = f"https://api.github.com/repos/{owner}/{repo}/issues/{pr_number}/comments"
        response = session.get(comments_url, headers=headers)
        if response.status_code != 200:
            print(f"获取issue comments失败，状态码: {response.status_code}")
            issue_comments = []
        else:
            issue_comments = response.json()
        
        # 获取PR review评论
        review_comments_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/comments"
        response = session.get(review_comments_url, headers=headers)
        if response.status_code != 200:
            print(f"获取review comments失败，状态码: {response.status_code}")
            review_comments = []
        else:
            review_comments = response.json()
        
        # 获取PR reviews
        reviews_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/reviews"
        response = session.get(reviews_url, headers=headers)
        if response.status_code != 200:
            print(f"获取reviews失败，状态码: {response.status_code}")
            reviews = []
        else:
            reviews = response.json()
        
        # 整理对话内容
        conversation = {
            "author": pr_data.get("user", {}).get("login", ""),
            "body": pr_data.get("body", ""),
            "issue_comments": [],
            "review_comments": [],
            "reviews": []
        }
        
        # 添加issue评论
        for comment in issue_comments:
            try:
                comment_data = {
                    "author": comment.get("user", {}).get("login", ""),
                    "created_at": comment.get("created_at", ""),
                    "body": comment.get("body", ""),
                    "type": "issue_comment"
                }
                conversation["issue_comments"].append(comment_data)
            except Exception as e:
                print(f"处理issue comment时出错: {str(e)}")
                continue
        
        # 添加review评论
        for comment in review_comments:
            try:
                comment_data = {
                    "author": comment.get("user", {}).get("login", ""),
                    "created_at": comment.get("created_at", ""),
                    "body": comment.get("body", ""),
                    "path": comment.get("path", ""),
                    "position": comment.get("position"),
                    "type": "review_comment"
                }
                conversation["review_comments"].append(comment_data)
            except Exception as e:
                print(f"处理review comment时出错: {str(e)}")
                continue
        
        # 添加reviews
        for review in reviews:
            try:
                review_data = {
                    "author": review.get("user", {}).get("login", ""),
                    "created_at": review.get("submitted_at", ""),
                    "body": review.get("body", ""),
                    "state": review.get("state", ""),
                    "type": "review"
                }
                conversation["reviews"].append(review_data)
            except Exception as e:
                print(f"处理review时出错: {str(e)}")
                continue
        
        return conversation
        
    except requests.exceptions.RequestException as e:
        print(f"网络请求错误: {str(e)}")
        return None
    except Exception as e:
        print(f"获取PR对话内容时出错: {str(e)}")
        print(f"错误详情: {type(e).__name__}")
        return None

def update_pr_data_with_conversation(pr_data, json_file="px4_navigator_prs.json"):
    """
    更新PR数据，为缺少对话的PR添加对话数据
    
    Args:
        pr_data: PR数据列表
        json_file: JSON文件路径
        
    Returns:
        list: 更新后的PR数据列表
    """
    # 加载GitHub token
    token = os.getenv("GITHUB_AUTHORIZATION")
    if not token:
        print("未找到有效的GitHub token，无法获取PR对话")
        return pr_data
        
    # 设置请求头
    headers = {
        "Authorization": f"{token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Github-PR-Conversation-Extractor"
    }
    
    # 创建会话以重用连接
    session = requests.Session()
    
    # 统计信息
    total = len(pr_data)
    need_conversation = 0
    processed = 0
    successful = 0
    failed = 0
    
    # 找出所有需要获取对话的PR
    prs_to_process = []
    for i, pr in enumerate(pr_data):
        if 'conversation' not in pr:
            prs_to_process.append((i, pr))
    
    need_conversation = len(prs_to_process)
    print(f"共有 {need_conversation} 个PR需要获取对话数据")
    
    # 没有需要处理的PR，直接返回
    if need_conversation == 0:
        print("所有PR已有对话数据，无需更新")
        return pr_data
    
    # 处理每个PR
    for i, (index, pr) in enumerate(tqdm(prs_to_process, desc="获取PR对话")):
        try:
            processed += 1
            pr_number = pr.get('number')
            
            print(f"\n[{processed}/{need_conversation}] 处理 PR #{pr_number}: {pr.get('title', '')}")
            
            # 获取对话内容
            conversation = get_pr_conversation(pr_number, headers, session)
            
            if conversation:
                # 更新PR数据
                pr_data[index]['conversation'] = conversation
                successful += 1
                
                # 每处理10个PR保存一次，避免数据丢失
                if successful % 10 == 0:
                    print(f"已成功处理 {successful} 个PR，正在保存中间结果...")
                    save_pr_data(pr_data, json_file)
            else:
                failed += 1
                print(f"获取PR #{pr_number} 的对话失败")
            
            # 避免触发GitHub API限制
            time.sleep(1)
            
        except Exception as e:
            failed += 1
            print(f"处理PR时出错: {str(e)}")
            continue
    
    # 保存最终结果
    if successful > 0:
        save_pr_data(pr_data, json_file)
    
    # 打印统计信息
    print(f"\n处理完成！")
    print(f"总计: {total} 个PR")
    print(f"需要获取对话: {need_conversation} 个")
    print(f"成功获取: {successful} 个")
    print(f"获取失败: {failed} 个")
    
    return pr_data

def main():
    # 记录开始时间
    start_time = time.time()
    print(f"开始运行时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 设置JSON文件路径
    json_file = "px4_navigator_prs.json"
    
    # 加载PR数据
    pr_data = load_pr_data(json_file)
    if not pr_data:
        print("无PR数据，程序退出")
        return
    
    # 更新PR数据，获取对话内容
    pr_data = update_pr_data_with_conversation(pr_data, json_file)
    
    # 记录结束时间并计算总耗时
    end_time = time.time()
    elapsed_time = end_time - start_time
    hours, remainder = divmod(elapsed_time, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    print(f"结束运行时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"总耗时: {int(hours)}小时 {int(minutes)}分钟 {seconds:.2f}秒")

if __name__ == "__main__":
    main()

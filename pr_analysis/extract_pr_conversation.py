import requests
import json
import time
from datetime import datetime
import re
import os

def get_pr_conversation(pr_number, headers):
    """
    获取PR的对话内容
    
    Args:
        pr_number: PR编号
        headers: GitHub API的请求头
        
    Returns:
        dict: 包含PR对话内容的字典
    """
    owner = "ArduPilot"
    repo = "ardupilot"
    api_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
    
    try:
        # 获取PR基本信息
        print(f"正在获取PR {pr_number} 的信息...")
        response = requests.get(api_url, headers=headers)
        
        # 检查API限制
        if response.status_code == 403:
            rate_limit = response.headers.get('X-RateLimit-Remaining', 'unknown')
            reset_time = response.headers.get('X-RateLimit-Reset', 0)
            if reset_time:
                reset_time = datetime.fromtimestamp(int(reset_time))
                print(f"API速率限制: 剩余请求数 {rate_limit}, 重置时间 {reset_time}")
            return None
            
        if response.status_code != 200:
            print(f"获取PR信息失败，状态码: {response.status_code}")
            print(f"错误信息: {response.text}")
            return None
        
        pr_data = response.json()
        
        # 获取PR评论（issue comments）
        comments_url = f"https://api.github.com/repos/{owner}/{repo}/issues/{pr_number}/comments"
        print("正在获取issue comments...")
        response = requests.get(comments_url, headers=headers)
        if response.status_code != 200:
            print(f"获取issue comments失败，状态码: {response.status_code}")
            print(f"错误信息: {response.text}")
            return None
        
        issue_comments = response.json()
        
        # 获取PR review评论
        review_comments_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/comments"
        print("正在获取review comments...")
        response = requests.get(review_comments_url, headers=headers)
        if response.status_code != 200:
            print(f"获取review comments失败，状态码: {response.status_code}")
            print(f"错误信息: {response.text}")
            return None
        
        review_comments = response.json()
        
        # 获取PR reviews
        reviews_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/reviews"
        print("正在获取reviews...")
        response = requests.get(reviews_url, headers=headers)
        if response.status_code != 200:
            print(f"获取reviews失败，状态码: {response.status_code}")
            print(f"错误信息: {response.text}")
            return None
        
        reviews = response.json()
        
        # 整理对话内容
        conversation = {
            "pr_number": pr_data.get("number"),
            "title": pr_data.get("title", ""),
            "state": pr_data.get("state", ""),
            "created_at": pr_data.get("created_at", ""),
            "updated_at": pr_data.get("updated_at", ""),
            "merged_at": pr_data.get("merged_at", ""),
            "closed_at": pr_data.get("closed_at", ""),
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
                if review.get("body") or review.get("state") != "COMMENTED":  # 保存有内容的review或非COMMENTED状态的review
                    review_data = {
                        "author": review.get("user", {}).get("login", ""),
                        "created_at": review.get("created_at", ""),
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

def save_conversation(conversation, pr_number, base_dir="extracted_test_cases"):
    """
    保存PR对话内容到JSON文件
    
    Args:
        conversation: PR对话内容
        pr_number: PR编号
        base_dir: 基础目录
    """
    # 确保PR目录存在
    pr_dir = os.path.join(base_dir, f"pr_{pr_number}")
    os.makedirs(pr_dir, exist_ok=True)
    
    # 生成文件名
    filename = "conversation.json"
    filepath = os.path.join(pr_dir, filename)
    
    # 保存为JSON文件
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(conversation, f, ensure_ascii=False, indent=2)
    
    print(f"对话内容已保存到: {filepath}")
    return filepath

def get_pr_numbers_from_dirs(base_dir="extracted_test_cases"):
    """
    从目录名称中获取PR编号列表
    
    Args:
        base_dir: 基础目录
        
    Returns:
        list: PR编号列表
    """
    pr_numbers = []
    
    if not os.path.exists(base_dir):
        print(f"错误：目录不存在 {base_dir}")
        return pr_numbers
        
    for dir_name in os.listdir(base_dir):
        if dir_name.startswith('pr_'):
            try:
                pr_number = dir_name.split('_')[1]
                pr_numbers.append(pr_number)
            except IndexError:
                print(f"警告：无法从目录名 {dir_name} 中提取PR编号")
                continue
    
    return pr_numbers

def process_all_prs(base_dir="extracted_test_cases"):
    """
    处理所有PR的对话内容
    
    Args:
        base_dir: 基础目录
    """
    # 从环境变量获取GitHub token
    github_token = os.environ.get('GITHUB_TOKEN')
    if not github_token:
        print("错误: 未设置GITHUB_TOKEN环境变量")
        print("请设置环境变量: export GITHUB_TOKEN=your_github_token_here")
        return
        
    # 设置请求头
    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Github-PR-Conversation-Extractor"
    }
    
    # 获取所有PR编号
    pr_numbers = get_pr_numbers_from_dirs(base_dir)
    if not pr_numbers:
        print("没有找到PR目录")
        return
        
    print(f"找到 {len(pr_numbers)} 个PR目录")
    
    # 统计信息
    total = len(pr_numbers)
    processed = 0
    failed = 0
    
    # 处理每个PR
    for pr_number in pr_numbers:
        try:
            processed += 1
            print(f"\n处理第 {processed}/{total} 个PR (#{pr_number})")

            
            # 获取对话内容
            conversation = get_pr_conversation(pr_number, headers)
            if conversation:
                save_conversation(conversation, pr_number, base_dir)
            else:
                failed += 1
                print(f"获取PR #{pr_number} 的对话内容失败")
            
            # 避免触发GitHub API限制
            print("等待1秒后继续...")
            time.sleep(1)
            
        except Exception as e:
            failed += 1
            print(f"处理PR #{pr_number} 时出错: {str(e)}")
            continue
    
    # 打印统计信息
    print(f"\n处理完成！")
    print(f"总计: {total} 个PR")
    print(f"成功: {processed - failed} 个")
    print(f"失败: {failed} 个")

def has_conversation_data(pr_info):
    """
    检查PR信息中是否已包含对话数据
    
    Args:
        pr_info: PR信息字典
        
    Returns:
        bool: 是否包含对话数据
    """
    if not pr_info.get('conversation'):
        return False
        
    # 检查conversation是否包含基本字段
    conversation = pr_info['conversation']
    if not isinstance(conversation, dict):
        return False
        
    # 检查是否至少有一个基本字段
    required_fields = ['author', 'body']
    for field in required_fields:
        if field not in conversation:
            return False
            
    return True

def process_ardu_changes_prs(base_dir="ardu_changes"):
    """
    处理ardu_changes目录下所有PR的对话内容，仅在没有对话数据时获取
    
    Args:
        base_dir: ardu_changes目录的路径
    """
    # 从环境变量获取GitHub token
    github_token = os.environ.get('GITHUB_TOKEN')
    if not github_token:
        print("错误: 未设置GITHUB_TOKEN环境变量")
        print("请设置环境变量: export GITHUB_TOKEN=your_github_token_here")
        return
        
    # 设置请求头
    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Github-PR-Conversation-Extractor"
    }
    
    # 统计信息
    total_prs = 0
    processed = 0
    skipped = 0
    failed = 0
    
    try:
        # 遍历所有PR目录
        for dir_name in os.listdir(base_dir):
            if not dir_name.startswith('pr_'):
                continue
                
            total_prs += 1
            pr_dir = os.path.join(base_dir, dir_name)
            pr_info_path = os.path.join(pr_dir, 'pr_info.json')
            
            if not os.path.exists(pr_info_path):
                print(f"跳过 {dir_name}: 未找到 pr_info.json")
                failed += 1
                continue
                
            try:
                # 读取pr_info.json
                with open(pr_info_path, 'r', encoding='utf-8') as f:
                    pr_info = json.load(f)
                
                pr_number = pr_info.get('number')
                if not pr_number:
                    print(f"跳过 {dir_name}: pr_info.json 中未找到 number 字段")
                    failed += 1
                    continue
                
                # 检查是否已有对话数据
                if has_conversation_data(pr_info):
                    print(f"跳过 PR #{pr_number} ({dir_name}): 已有对话数据")
                    skipped += 1
                    continue
                    
                print(f"\n处理 PR #{pr_number} ({dir_name})...")
                
                # 获取PR对话内容
                conversation = get_pr_conversation(pr_number, headers)
                if not conversation:
                    print(f"获取 PR #{pr_number} 的对话内容失败")
                    failed += 1
                    continue
                
                # 提取需要的字段
                conversation_extract = {
                    "author": conversation.get("author", ""),
                    "body": conversation.get("body", ""),
                    "issue_comments": conversation.get("issue_comments", []),
                    "review_comments": conversation.get("review_comments", []),
                    "reviews": conversation.get("reviews", [])
                }
                
                # 更新pr_info.json
                pr_info['conversation'] = conversation_extract
                
                # 保存更新后的文件
                with open(pr_info_path, 'w', encoding='utf-8') as f:
                    json.dump(pr_info, f, ensure_ascii=False, indent=2)
                
                processed += 1
                print(f"已更新 {pr_info_path}")
                
                # 避免触发GitHub API限制
                print("等待0.1秒后继续...")
                time.sleep(0.1)
                
            except Exception as e:
                failed += 1
                print(f"处理 {dir_name} 时出错: {str(e)}")
                continue
        
        # 打印统计信息
        print(f"\n处理完成！")
        print(f"总计: {total_prs} 个PR")
        print(f"跳过（已有数据）: {skipped} 个")
        print(f"成功更新: {processed} 个")
        print(f"失败: {failed} 个")
        
    except Exception as e:
        print(f"遍历目录时出错: {str(e)}")
        return

def main():
    # 处理ardu_changes目录下的PR
    print("处理 ardu_changes 目录下的PR...")
    process_ardu_changes_prs()
    
    # 处理原有的extracted_test_cases目录（如果需要）
    # print("\n处理 extracted_test_cases 目录下的PR...")
    # process_all_prs("extracted_test_cases")

if __name__ == "__main__":
    main() 
import requests
import json
import time
import os
import re
from datetime import datetime, timedelta
import threading
from queue import Queue
from concurrent.futures import ThreadPoolExecutor, as_completed

def load_existing_prs(output_file="px4_navigator_prs.json", output_dir="px4_navigator_prs"):
    """
    加载已有的PR数据
    
    Args:
        output_file: 主PR数据文件
        output_dir: PR详情目录
        
    Returns:
        (list, set): PR列表和已查询PR编号集合
    """
    existing_prs = []
    existing_pr_numbers = set()
    
    # 尝试加载主数据文件
    if os.path.exists(output_file):
        try:
            with open(output_file, 'r', encoding='utf-8') as f:
                existing_prs = json.load(f)
                print(f"已加载 {len(existing_prs)} 个PR数据")
                
                # 收集已有PR编号
                for pr in existing_prs:
                    if 'number' in pr:
                        existing_pr_numbers.add(pr['number'])
        except Exception as e:
            print(f"加载已有PR数据时出错: {str(e)}")
    
    # 检查PR详情目录
    if os.path.exists(output_dir):
        for dir_name in os.listdir(output_dir):
            if dir_name.startswith('pr_'):
                try:
                    pr_number = int(dir_name.split('_')[1])
                    existing_pr_numbers.add(pr_number)
                except (IndexError, ValueError):
                    pass
    
    print(f"已有 {len(existing_pr_numbers)} 个PR的编号记录")
    return existing_prs, existing_pr_numbers

def search_navigator_prs(repo="PX4/PX4-Autopilot", max_pages=1000, disable_proxy=True, existing_pr_numbers=None):
    """
    搜索PX4/PX4-Autopilot仓库中修改了src/modules/navigator文件夹下文件的PR
    
    Args:
        repo: 仓库名称，格式为"owner/repo"
        max_pages: 最大页数限制
        disable_proxy: 是否禁用代理
        existing_pr_numbers: 已存在的PR编号集合，避免重复查询
        
    Returns:
        包含匹配PR信息的列表
    """
    # 初始化已存在的PR编号集合
    if existing_pr_numbers is None:
        existing_pr_numbers = set()
    
    # 使用GitHub搜索API
    api_url = "https://api.github.com/search/issues"
    
    # 存储所有找到的PR
    all_prs = []
    
    # GitHub访问令牌，如果有的话
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Github-PR-Navigator-Scraper"
    }
    
    # 如果设置了环境变量，使用它
    if os.getenv("GITHUB_AUTHORIZATION"):
        headers["Authorization"] = os.getenv("GITHUB_AUTHORIZATION")
    
    # 构建查询参数，搜索所有PR，不使用路径过滤
    query = f"repo:{repo} is:pull-request"
    
    page = 1
    total_found = 0
    navigator_found = 0
    skipped = 0
    
    # 设置会话以禁用代理
    session = requests.Session()
    if disable_proxy:
        session.proxies = {
            'http': None,
            'https': None
        }
    
    while page <= max_pages:
        params = {
            "q": query,
            "per_page": 100,
            "page": page
        }
        
        print(f"正在获取第{page}页结果...")
        try:
            response = session.get(api_url, params=params, headers=headers)
            
            # 检查API速率限制
            if response.status_code == 403 and 'rate limit' in response.text.lower():
                rate_limit_reset = int(response.headers.get('X-RateLimit-Reset', 0))
                current_time = int(time.time())
                wait_time = rate_limit_reset - current_time + 5
                if wait_time > 0:
                    print(f"达到API速率限制，等待{wait_time}秒后继续...")
                    time.sleep(wait_time)
                    continue
            
            # 处理其他错误
            if response.status_code != 200:
                print(f"API请求失败，状态码: {response.status_code}")
                print(f"错误信息: {response.text}")
                break
            
            data = response.json()
            items = data.get('items', [])
            total_in_page = len(items)
            
            if not items:
                print("未找到更多结果或已到达最后一页")
                break
                
            print(f"本页找到 {total_in_page} 个PR，开始逐个验证...")
            
            # 处理搜索结果
            for item in items:
                # 获取PR的详细信息，包括merged状态
                pr_url = item.get('pull_request', {}).get('url')
                pr_number = item.get('number')
                
                # 如果PR已存在，则跳过
                if pr_number in existing_pr_numbers:
                    print(f"跳过已存在的PR #{pr_number}: {item.get('title')}")
                    skipped += 1
                    continue
                
                if pr_url:
                    try:
                        pr_response = session.get(pr_url, headers=headers)
                        if pr_response.status_code == 200:
                            pr_data = pr_response.json()
                            
                            # 验证PR是否修改了navigator文件夹
                            print(f"验证PR #{pr_number}: {item.get('title')}")
                            verified = verify_navigator_changes(pr_data['number'], headers, repo, session)
                            if verified:
                                # 收集详细信息
                                pr_info = {
                                    "title": item.get('title'),
                                    "url": item.get('html_url'),
                                    "api_url": item.get('url'),
                                    "number": item.get('number'),
                                    "created_at": item.get('created_at'),
                                    "updated_at": item.get('updated_at'),
                                    "merged": pr_data.get('merged', False),
                                    "merged_at": pr_data.get('merged_at'),
                                    "state": item.get('state'),
                                    "labels": [label.get('name') for label in item.get('labels', [])]
                                }
                                
                                # 获取PR对话内容
                                conversation = get_pr_conversation(pr_data['number'], headers, repo.split('/')[0], repo.split('/')[1], session)
                                if conversation:
                                    pr_info['conversation'] = conversation
                                
                                all_prs.append(pr_info)
                                navigator_found += 1
                                existing_pr_numbers.add(pr_number)  # 添加到已查询集合
                                print(f"✓ PR #{pr_info['number']} 修改了navigator文件夹: {pr_info['title']}")
                                
                                # 中途保存结果，避免丢失数据
                                if navigator_found % 10 == 0:
                                    save_partial_results(all_prs, f"px4_navigator_prs_partial_{navigator_found}.json")
                            else:
                                print(f"✗ PR #{pr_number} 未修改navigator文件夹")
                                existing_pr_numbers.add(pr_number)  # 也将未匹配的PR添加到已查询集合
                            
                            # 短暂暂停以避免触发API限制
                            time.sleep(0.5)
                    except Exception as e:
                        print(f"获取PR详细信息时出错: {str(e)}")
            
            total_found += (total_in_page - skipped)
            print(f"已处理 {total_found} 个PR, 跳过 {skipped} 个, 找到 {navigator_found} 个修改了navigator的PR")
            
            # 检查是否有下一页
            if len(items) < 100:
                print(f"已到达最后一页，共找到{navigator_found}个匹配navigator的PR")
                break
            
            page += 1
            
            # GitHub API有速率限制，暂停一下以避免被限制
            time.sleep(2)
        except Exception as e:
            print(f"请求出错: {str(e)}")
            time.sleep(5)
            continue
    
    return all_prs

def verify_navigator_changes(pr_number, headers, repo="PX4/PX4-Autopilot", session=None):
    """
    验证PR是否修改了navigator文件夹下的文件
    """
    api_url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}/files"
    
    if session is None:
        session = requests.Session()
        session.proxies = {
            'http': None,
            'https': None
        }
    
    # 添加重试机制
    for attempt in range(3):
        try:
            response = session.get(api_url, headers=headers, timeout=10)
            if response.status_code == 200:
                break
            elif response.status_code == 403:
                print(f"API速率限制，等待60秒...")
                time.sleep(60)
                continue
            else:
                print(f"获取PR文件失败，状态码: {response.status_code}")
                return False
        except Exception as e:
            print(f"请求失败，尝试重试 ({attempt + 1}/3): {str(e)}")
            time.sleep(5)
            continue
    else:
        print(f"获取PR #{pr_number} 文件失败，已达到最大重试次数")
        return False
    
    try:
        files = response.json()
        
        # 检查是否修改了navigator文件夹下的文件
        for file in files:
            filename = file.get("filename", "")
            if filename.startswith("src/modules/navigator/"):
                return True
        
        return False
    except Exception as e:
        print(f"解析PR #{pr_number}的文件时出错: {str(e)}")
        return False

def get_pr_conversation(pr_number, headers, owner, repo, session=None):
    """
    获取PR的对话内容
    
    Args:
        pr_number: PR编号
        headers: GitHub API的请求头
        owner: 仓库所有者
        repo: 仓库名称
        session: 请求会话
        
    Returns:
        dict: 包含PR对话内容的字典
    """
    if session is None:
        session = requests.Session()
        session.proxies = {
            'http': None,
            'https': None
        }
    
    api_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
    
    try:
        # 获取PR基本信息
        print(f"正在获取PR {pr_number} 的对话信息...")
        response = session.get(api_url, headers=headers)
        
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

def save_partial_results(results, filename):
    """保存中间结果，防止程序中断丢失数据"""
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"已保存中间结果到 {filename}")
    except Exception as e:
        print(f"保存中间结果失败: {str(e)}")

def search_navigator_prs_by_date_range(start_date, end_date, interval_days=90, repo="PX4/PX4-Autopilot", disable_proxy=True, result_queue=None, thread_id=None, existing_pr_numbers=None):
    """
    按时间间隔搜索PX4/PX4-Autopilot仓库，分段获取所有修改了navigator文件夹的PR
    
    Args:
        start_date: 开始日期，格式为"YYYY-MM-DD"的字符串或datetime对象
        end_date: 结束日期，格式为"YYYY-MM-DD"的字符串或datetime对象
        interval_days: 时间间隔天数，默认90天
        repo: 仓库名称，格式为"owner/repo"
        disable_proxy: 是否禁用代理
        result_queue: 结果队列，用于多线程
        thread_id: 线程ID，用于标识
        existing_pr_numbers: 已存在的PR编号集合，避免重复查询
        
    Returns:
        包含所有时间段搜索结果的合并列表
    """
    # 初始化已存在的PR编号集合
    if existing_pr_numbers is None:
        existing_pr_numbers = set()
    
    # 转换日期格式
    if isinstance(start_date, str):
        start_date = datetime.strptime(start_date, "%Y-%m-%d")
    if isinstance(end_date, str):
        end_date = datetime.strptime(end_date, "%Y-%m-%d")
    
    # 如果未指定结束日期，使用当前日期
    if not end_date:
        end_date = datetime.now()
    
    thread_prefix = f"[线程{thread_id}] " if thread_id is not None else ""
    print(f"{thread_prefix}开始按时间段搜索，从 {start_date.date()} 到 {end_date.date()}, 间隔 {interval_days} 天")
    
    all_results = []
    current_date = start_date
    segment_count = 0
    skipped = 0
    
    # 解析仓库信息
    owner, repo_name = repo.split('/')
    
    # 创建会话并禁用代理
    session = requests.Session()
    if disable_proxy:
        session.proxies = {
            'http': None,
            'https': None
        }
    
    while current_date < end_date:
        segment_count += 1
        # 计算下一个时间节点
        next_date = current_date + timedelta(days=interval_days)
        if next_date > end_date:
            next_date = end_date
        
        # 格式化日期为ISO格式
        current_iso = current_date.strftime("%Y-%m-%d")
        next_iso = next_date.strftime("%Y-%m-%d")
        
        print(f"{thread_prefix}===== 搜索时间段 {segment_count}: {current_iso} 到 {next_iso} =====")
        
        # 构建API URL和参数
        api_url = "https://api.github.com/search/issues"
        query = f"repo:{repo} is:pull-request created:{current_iso}..{next_iso}"
        
        # GitHub访问令牌
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Github-PR-Navigator-Scraper"
        }
        
        if os.getenv("GITHUB_AUTHORIZATION"):
            headers["Authorization"] = os.getenv("GITHUB_AUTHORIZATION")
        
        # 分页获取结果
        page = 1
        max_pages = 10  # 每个时间段最多获取10页
        navigator_found = 0
        
        while page <= max_pages:
            params = {
                "q": query,
                "per_page": 100,
                "page": page
            }
            
            print(f"{thread_prefix}  获取第{page}页结果...")
            try:
                response = session.get(api_url, params=params, headers=headers)
                
                # 处理API限制
                if response.status_code == 403:
                    rate_limit_reset = int(response.headers.get('X-RateLimit-Reset', 0))
                    current_time = int(time.time())
                    wait_time = rate_limit_reset - current_time + 5
                    if wait_time > 0:
                        print(f"{thread_prefix}  达到API速率限制，等待{wait_time}秒后继续...")
                        time.sleep(wait_time)
                        continue
                
                if response.status_code != 200:
                    print(f"{thread_prefix}  API请求失败，状态码: {response.status_code}")
                    break
                
                data = response.json()
                items = data.get('items', [])
                
                if not items:
                    print(f"{thread_prefix}  未找到更多结果或已到达最后一页")
                    break
                
                print(f"{thread_prefix}  本页找到 {len(items)} 个PR，开始逐个验证...")
                page_skipped = 0
                
                # 处理搜索结果
                for item in items:
                    pr_url = item.get('pull_request', {}).get('url')
                    pr_number = item.get('number')
                    
                    # 如果PR已存在，则跳过
                    if pr_number in existing_pr_numbers:
                        print(f"{thread_prefix}  跳过已存在的PR #{pr_number}: {item.get('title')}")
                        page_skipped += 1
                        skipped += 1
                        continue
                    
                    if pr_url:
                        try:
                            pr_response = session.get(pr_url, headers=headers)
                            if pr_response.status_code == 200:
                                pr_data = pr_response.json()
                                
                                # 验证PR是否修改了navigator文件夹
                                print(f"{thread_prefix}  验证PR #{pr_number}: {item.get('title')}")
                                verified = verify_navigator_changes(pr_data['number'], headers, repo, session)
                                if verified:
                                    pr_info = {
                                        "title": item.get('title'),
                                        "url": item.get('html_url'),
                                        "number": item.get('number'),
                                        "created_at": item.get('created_at'),
                                        "merged": pr_data.get('merged', False),
                                        "merged_at": pr_data.get('merged_at'),
                                        "state": item.get('state')
                                    }
                                    
                                    # 获取PR对话内容
                                    conversation = get_pr_conversation(pr_data['number'], headers, owner, repo_name, session)
                                    if conversation:
                                        pr_info['conversation'] = conversation
                                        
                                    all_results.append(pr_info)
                                    navigator_found += 1
                                    existing_pr_numbers.add(pr_number)  # 添加到已查询集合
                                    print(f"{thread_prefix}  ✓ PR #{pr_info['number']} 修改了navigator文件夹: {pr_info['title']}")
                                    
                                    # 中途保存结果
                                    if navigator_found % 10 == 0:
                                        temp_file = f"px4_navigator_prs_temp_{thread_id}_{segment_count}_{navigator_found}.json"
                                        save_partial_results(all_results, temp_file)
                                else:
                                    print(f"{thread_prefix}  ✗ PR #{pr_number} 未修改navigator文件夹")
                                    existing_pr_numbers.add(pr_number)  # 也将未匹配的PR添加到已查询集合
                                
                                time.sleep(0.5)
                        except Exception as e:
                            print(f"{thread_prefix}  获取PR详细信息时出错: {str(e)}")
                
                print(f"{thread_prefix}  本页处理: {len(items)-page_skipped} 个PR, 跳过: {page_skipped} 个")
                
                # 检查是否有下一页
                if len(items) < 100:
                    break
                
                page += 1
                time.sleep(2)
            except Exception as e:
                print(f"{thread_prefix}  请求出错: {str(e)}")
                time.sleep(5)
                continue
        
        print(f"{thread_prefix}  时间段 {segment_count} 找到 {navigator_found} 个修改了navigator的PR, 跳过 {skipped} 个")
        
        # 移到下一个时间段
        current_date = next_date
        time.sleep(1)  # 减少等待时间
    
    print(f"{thread_prefix} 总计: 找到 {len(all_results)} 个修改了navigator的PR, 跳过 {skipped} 个")
    
    # 如果使用多线程，将结果放入队列
    if result_queue is not None:
        result_queue.put(all_results)
        return None
    
    return all_results

def search_with_threads(repo="PX4/PX4-Autopilot", start_date="2016-01-01", end_date=None, disable_proxy=True, existing_pr_numbers=None):
    """
    使用多线程加速搜索过程
    
    Args:
        repo: 仓库名称，格式为"owner/repo"
        start_date: 开始日期，格式为"YYYY-MM-DD"的字符串
        end_date: 结束日期，格式为"YYYY-MM-DD"的字符串，默认为当前日期
        disable_proxy: 是否禁用代理
        existing_pr_numbers: 已存在的PR编号集合，避免重复查询
    
    Returns:
        包含所有时间段搜索结果的合并列表
    """
    # 初始化已存在的PR编号集合
    if existing_pr_numbers is None:
        existing_pr_numbers = set()
    
    # 如果未指定结束日期，使用当前日期
    if end_date is None:
        end_date = datetime.now().strftime("%Y-%m-%d")
    
    # 转换为datetime对象
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    
    # 计算总天数
    total_days = (end_dt - start_dt).days
    segment_days = total_days // 4  # 将时间范围分为4段
    
    # 创建4个线程的日期范围
    date_ranges = []
    for i in range(4):
        range_start = start_dt + timedelta(days=i * segment_days)
        range_end = start_dt + timedelta(days=(i + 1) * segment_days) if i < 3 else end_dt
        date_ranges.append((range_start.strftime("%Y-%m-%d"), range_end.strftime("%Y-%m-%d")))
    
    print("将时间范围分为4段进行并行搜索:")
    for i, (s, e) in enumerate(date_ranges):
        print(f"线程 {i+1}: {s} 到 {e}")
    
    # 为每个线程提供一份已存在PR编号的副本，避免线程冲突
    shared_pr_numbers = set(existing_pr_numbers)  # 创建副本
    
    # 创建线程池
    all_results = []
    with ThreadPoolExecutor(max_workers=4) as executor:
        # 提交任务
        futures = []
        for i, (s_date, e_date) in enumerate(date_ranges):
            future = executor.submit(
                search_navigator_prs_by_date_range, 
                s_date, e_date, 
                90, repo, disable_proxy,
                None, i+1, shared_pr_numbers
            )
            futures.append(future)
        
        # 收集结果
        for future in as_completed(futures):
            try:
                result = future.result()
                if result:
                    all_results.extend(result)
            except Exception as e:
                print(f"线程执行出错: {str(e)}")
    
    return all_results

def merge_pr_results(new_prs, existing_prs):
    """
    合并新的PR结果和现有的PR结果
    
    Args:
        new_prs: 新的PR列表
        existing_prs: 现有的PR列表
        
    Returns:
        合并后的PR列表
    """
    # 创建一个PR编号到PR数据的映射
    pr_map = {}
    for pr in existing_prs:
        if 'number' in pr:
            pr_map[pr['number']] = pr
    
    # 添加新的PR数据
    for pr in new_prs:
        if 'number' in pr:
            pr_map[pr['number']] = pr
    
    # 转换回列表
    merged_prs = list(pr_map.values())
    return merged_prs

def main():
    """主函数"""
    print("开始查找PX4/PX4-Autopilot仓库中修改了src/modules/navigator的PR...")
    
    # 配置搜索参数
    repo = "PX4/PX4-Autopilot"
    use_date_range = True  # 设置为True启用按日期范围搜索
    disable_proxy = True   # 禁用代理设置
    use_threads = True     # 使用多线程
    
    # 设置输出文件和目录
    output_file = "px4_navigator_prs.json"
    output_dir = "px4_navigator_prs"
    
    # 加载已有的PR数据
    print("加载已有的PR数据...")
    existing_prs, existing_pr_numbers = load_existing_prs(output_file, output_dir)
    
    # 设置日期范围
    start_date = "2015-01-01"  # PX4项目开始时间或更早
    end_date =  "2016-01-01"  # 当前日期
    interval_days = 180  # 6个月为一个区间
    
    # 查询PR数据
    if use_threads and use_date_range:
        print(f"使用多线程搜索：从 {start_date} 到 {end_date}")
        new_prs = search_with_threads(repo, start_date, end_date, disable_proxy, existing_pr_numbers)
    elif use_date_range:
        print(f"使用日期范围搜索：从 {start_date} 到 {end_date}, 间隔 {interval_days} 天")
        new_prs = search_navigator_prs_by_date_range(start_date, end_date, interval_days, repo, disable_proxy, None, None, existing_pr_numbers)
    else:
        # 不使用日期范围
        print("使用标准搜索（可能受1000个结果的限制）")
        new_prs = search_navigator_prs(repo, disable_proxy=disable_proxy, existing_pr_numbers=existing_pr_numbers)
    
    # 合并结果
    if new_prs:
        print(f"\n新搜索结果:")
        print(f"本次找到{len(new_prs)}个新的修改了src/modules/navigator的PR\n")
        
        # 合并新旧PR数据
        all_prs = merge_pr_results(new_prs, existing_prs)
        
        # 统计信息
        merged_count = sum(1 for pr in all_prs if pr.get('merged', False))
        print(f"合并后总共有 {len(all_prs)} 个PR")
        print(f"其中已合并的PR数量: {merged_count}")
        
        # 保存结果到JSON文件
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(all_prs, f, ensure_ascii=False, indent=2)
        
        print(f"搜索结果已保存到 {output_file}")
        
        # 创建输出目录，保存每个PR的详细信息
        os.makedirs(output_dir, exist_ok=True)
        
        # 保存每个PR的详细信息
        for pr_info in new_prs:  # 只保存新的PR信息
            pr_number = pr_info.get('number')
            if pr_number:
                pr_dir = os.path.join(output_dir, f"pr_{pr_number}")
                os.makedirs(pr_dir, exist_ok=True)
                
                # 保存PR信息
                with open(os.path.join(pr_dir, "pr_info.json"), "w", encoding="utf-8") as f:
                    json.dump(pr_info, f, ensure_ascii=False, indent=2)
        
        if new_prs:            
            print(f"新PR的详细信息已保存到 {output_dir} 目录")
        else:
            print("没有找到新的PR，无需保存")
    else:
        print("未找到新的修改了src/modules/navigator的PR")

if __name__ == "__main__":
    main()

import requests
import json
import time
import os
from datetime import datetime, timedelta
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

def save_partial_results(results, filename):
    """保存中间结果，防止程序中断丢失数据"""
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"已保存中间结果到 {filename}")
    except Exception as e:
        print(f"保存中间结果失败: {str(e)}")

def search_from_issues_api(date_range, repo, headers, session, existing_pr_numbers, thread_id=None):
    """
    使用GitHub Issues API搜索特定日期范围内的PR
    
    Args:
        date_range: 元组 (start_date, end_date)，日期格式为"YYYY-MM-DD"
        repo: 仓库名称 "owner/repo"
        headers: API请求头
        session: 请求会话
        existing_pr_numbers: 已存在的PR编号集合
        thread_id: 线程ID
        
    Returns:
        找到的PR列表
    """
    start_date, end_date = date_range
    thread_prefix = f"[线程{thread_id}] " if thread_id is not None else ""
    
    print(f"{thread_prefix}使用Issues API搜索时间段: {start_date} 到 {end_date}")
    
    # 使用GitHub搜索API
    api_url = "https://api.github.com/search/issues"
    query = f"repo:{repo} is:pull-request created:{start_date}..{end_date}"
    
    all_prs = []
    page = 1
    max_pages = 10
    
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
            
            print(f"{thread_prefix}  本页找到 {len(items)} 个PR，开始验证...")
            
            # 处理搜索结果
            for item in items:
                pr_url = item.get('pull_request', {}).get('url')
                pr_number = item.get('number')
                
                # 如果PR已存在，则跳过
                if pr_number in existing_pr_numbers:
                    print(f"{thread_prefix}  跳过已存在的PR #{pr_number}")
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
                                    "number": pr_number,
                                    "created_at": item.get('created_at'),
                                    "merged": pr_data.get('merged', False),
                                    "merged_at": pr_data.get('merged_at'),
                                    "state": item.get('state')
                                }
                                
                                all_prs.append(pr_info)
                                existing_pr_numbers.add(pr_number)
                                print(f"{thread_prefix}  ✓ PR #{pr_info['number']} 修改了navigator文件夹")
                            else:
                                print(f"{thread_prefix}  ✗ PR #{pr_number} 未修改navigator文件夹")
                                existing_pr_numbers.add(pr_number)
                            
                            time.sleep(0.5)
                    except Exception as e:
                        print(f"{thread_prefix}  处理PR详细信息时出错: {str(e)}")
            
            # 检查是否有下一页
            if len(items) < 100:
                break
            
            page += 1
            time.sleep(2)
        except Exception as e:
            print(f"{thread_prefix}  请求出错: {str(e)}")
            time.sleep(5)
    
    return all_prs

def search_from_pulls_api(date_range, repo, headers, session, existing_pr_numbers, thread_id=None):
    """
    使用GitHub Pulls API搜索特定日期范围内的PR
    
    Args:
        date_range: 元组 (start_date, end_date)，日期格式为"YYYY-MM-DD"
        repo: 仓库名称 "owner/repo"
        headers: API请求头
        session: 请求会话
        existing_pr_numbers: 已存在的PR编号集合
        thread_id: 线程ID
        
    Returns:
        找到的PR列表
    """
    start_date, end_date = date_range
    thread_prefix = f"[线程{thread_id}] " if thread_id is not None else ""
    
    print(f"{thread_prefix}使用Pulls API搜索时间段: {start_date} 到 {end_date}")
    
    # 解析仓库信息
    owner, repo_name = repo.split('/')
    
    # 直接使用pulls API端点
    api_url = f"https://api.github.com/repos/{owner}/{repo_name}/pulls"
    
    all_prs = []
    page = 1
    max_pages = 10
    
    while page <= max_pages:
        params = {
            "state": "all",
            "per_page": 100,
            "page": page,
            "sort": "created",
            "direction": "desc"
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
            
            pulls = response.json()
            
            if not pulls:
                print(f"{thread_prefix}  未找到更多结果或已到达最后一页")
                break
            
            print(f"{thread_prefix}  本页找到 {len(pulls)} 个PR，开始验证...")
            
            # 过滤指定日期范围内的PR
            filtered_pulls = []
            for pr in pulls:
                created_at = pr.get('created_at', '')
                if not created_at:
                    continue
                
                created_date = created_at.split('T')[0]  # 提取日期部分
                
                # 检查是否在日期范围内
                if start_date <= created_date <= end_date:
                    filtered_pulls.append(pr)
                elif created_date < start_date:
                    # 由于按创建时间降序排序，如果遇到早于开始日期的PR，可以停止
                    print(f"{thread_prefix}  达到日期范围下限，停止搜索")
                    break
            
            # 处理过滤后的结果
            for pr_data in filtered_pulls:
                pr_number = pr_data.get('number')
                
                # 如果PR已存在，则跳过
                if pr_number in existing_pr_numbers:
                    print(f"{thread_prefix}  跳过已存在的PR #{pr_number}")
                    continue
                
                try:
                    # 验证PR是否修改了navigator文件夹
                    print(f"{thread_prefix}  验证PR #{pr_number}: {pr_data.get('title')}")
                    verified = verify_navigator_changes(pr_number, headers, repo, session)
                    if verified:
                        pr_info = {
                            "title": pr_data.get('title'),
                            "url": pr_data.get('html_url'),
                            "number": pr_number,
                            "created_at": pr_data.get('created_at'),
                            "merged": pr_data.get('merged', False),
                            "merged_at": pr_data.get('merged_at'),
                            "state": pr_data.get('state')
                        }
                        
                        all_prs.append(pr_info)
                        existing_pr_numbers.add(pr_number)
                        print(f"{thread_prefix}  ✓ PR #{pr_info['number']} 修改了navigator文件夹")
                    else:
                        print(f"{thread_prefix}  ✗ PR #{pr_number} 未修改navigator文件夹")
                        existing_pr_numbers.add(pr_number)
                    
                    time.sleep(0.5)
                except Exception as e:
                    print(f"{thread_prefix}  处理PR详细信息时出错: {str(e)}")
            
            # 如果过滤后没有PR或已到达日期范围下限，则停止
            if not filtered_pulls:
                break
            
            # 检查是否有下一页
            if len(pulls) < 100:
                break
            
            page += 1
            time.sleep(2)
        except Exception as e:
            print(f"{thread_prefix}  请求出错: {str(e)}")
            time.sleep(5)
    
    return all_prs

def search_combined_with_date_range_thread(date_range, repo, disable_proxy, existing_pr_numbers, thread_id):
    """
    结合使用issues和pulls API搜索特定日期范围内的PR（多线程版本）
    
    Args:
        date_range: 元组 (start_date, end_date)，日期格式为"YYYY-MM-DD"
        repo: 仓库名称 "owner/repo"
        disable_proxy: 是否禁用代理
        existing_pr_numbers: 已存在的PR编号集合
        thread_id: 线程ID
        
    Returns:
        找到的PR列表
    """
    # 创建副本避免修改原始集合
    thread_pr_numbers = set(existing_pr_numbers)
    
    # GitHub访问令牌
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Github-PR-Navigator-Scraper"
    }
    
    if os.getenv("GITHUB_AUTHORIZATION"):
        headers["Authorization"] = os.getenv("GITHUB_AUTHORIZATION")
    
    # 设置会话以禁用代理
    session = requests.Session()
    if disable_proxy:
        session.proxies = {
            'http': None,
            'https': None
        }
    
    # 使用issues API搜索
    issues_prs = search_from_issues_api(date_range, repo, headers, session, thread_pr_numbers, thread_id)
    
    # 更新线程PR集合
    for pr in issues_prs:
        if 'number' in pr:
            thread_pr_numbers.add(pr['number'])
    
    # 使用pulls API搜索
    pulls_prs = search_from_pulls_api(date_range, repo, headers, session, thread_pr_numbers, thread_id)
    
    # 合并结果
    all_prs = []
    all_prs.extend(issues_prs)
    all_prs.extend(pulls_prs)
    
    # 保存线程中间结果
    save_partial_results(all_prs, f"px4_navigator_prs_thread_{thread_id}.json")
    
    return all_prs

def search_with_threads_combined(repo="PX4/PX4-Autopilot", start_date=None, end_date=None, disable_proxy=True, existing_pr_numbers=None):
    """
    使用多线程结合issues和pulls API进行搜索
    
    Args:
        repo: 仓库名称，格式为"owner/repo"
        start_date: 开始日期，格式为"YYYY-MM-DD"的字符串
        end_date: 结束日期，格式为"YYYY-MM-DD"的字符串，默认为当前日期
        disable_proxy: 是否禁用代理
        existing_pr_numbers: 已存在的PR编号集合
        
    Returns:
        包含所有PR的合并列表
    """
    # 初始化已存在的PR编号集合
    if existing_pr_numbers is None:
        existing_pr_numbers = set()
    
    # 设置默认日期
    if start_date is None:
        start_date = "2024-01-01"
    if end_date is None:
        end_date = datetime.now().strftime("%Y-%m-%d")
    
    # 转换为datetime对象
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    
    # 计算总天数
    total_days = (end_dt - start_dt).days
    segment_days = max(1, total_days // 4)  # 将时间范围分为4段，至少1天
    
    # 创建4个线程的日期范围
    date_ranges = []
    for i in range(4):
        range_start = start_dt + timedelta(days=i * segment_days)
        range_end = start_dt + timedelta(days=(i + 1) * segment_days) if i < 3 else end_dt
        date_ranges.append((range_start.strftime("%Y-%m-%d"), range_end.strftime("%Y-%m-%d")))
    
    print("将时间范围分为4段进行并行搜索:")
    for i, (s, e) in enumerate(date_ranges):
        print(f"线程 {i+1}: {s} 到 {e}")
    
    # 创建共享的PR编号集合副本
    shared_pr_numbers = set(existing_pr_numbers)
    
    # 创建线程池
    all_results = []
    with ThreadPoolExecutor(max_workers=4) as executor:
        # 提交任务
        futures = []
        for i, date_range in enumerate(date_ranges):
            future = executor.submit(
                search_combined_with_date_range_thread, 
                date_range, repo, disable_proxy,
                shared_pr_numbers, i+1
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
    disable_proxy = True   # 禁用代理设置
    
    # 设置输出文件和目录
    output_file = "px4_navigator_prs.json"
    output_dir = "px4_navigator_prs"
    
    # 加载已有的PR数据
    print("加载已有的PR数据...")
    existing_prs, existing_pr_numbers = load_existing_prs(output_file, output_dir)
    
    # 设置日期范围
    start_date = "2015-01-01"  # 搜索开始日期
    end_date = "2024-01-01"    # 搜索结束日期
    
    print(f"使用多线程结合issues和pulls API搜索：从 {start_date} 到 {end_date}")
    new_prs = search_with_threads_combined(repo, start_date, end_date, disable_proxy, existing_pr_numbers)
    
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
        for pr_info in new_prs:
            pr_number = pr_info.get('number')
            if pr_number:
                pr_dir = os.path.join(output_dir, f"pr_{pr_number}")
                os.makedirs(pr_dir, exist_ok=True)
                
                # 保存PR信息
                with open(os.path.join(pr_dir, "pr_info.json"), "w", encoding="utf-8") as f:
                    json.dump(pr_info, f, ensure_ascii=False, indent=2)
        
        print(f"新PR的详细信息已保存到 {output_dir} 目录")
    else:
        print("未找到新的修改了src/modules/navigator的PR")

if __name__ == "__main__":
    main()

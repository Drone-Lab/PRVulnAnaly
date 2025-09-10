import os
import requests
import json
import re
import time
import datetime
import threading
from concurrent.futures import ThreadPoolExecutor

def load_json_file(json_file):
    """
    加载JSON文件
    
    Args:
        json_file: JSON文件路径
        
    Returns:
        加载的JSON数据
    """
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        print(f"成功加载JSON文件，共有 {len(data)} 个记录")
        return data
    except FileNotFoundError:
        print(f"文件不存在: {json_file}")
        return {}
    except Exception as e:
        print(f"加载JSON文件失败: {str(e)}")
        return {}

def save_json_file(data, output_file):
    """
    保存JSON数据到文件
    
    Args:
        data: 要保存的数据
        output_file: 输出文件路径
    """
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"成功保存数据到: {output_file}")
        return True
    except Exception as e:
        print(f"保存数据失败: {str(e)}")
        return False

def get_previous_commit_info(blob_url):
    """
    从blob_url获取前一个提交的信息
    
    Args:
        blob_url: 文件在GitHub上的URL
        
    Returns:
        (previous_commit, previous_url): 前一个提交哈希和API URL
    """
    # 从blob_url中提取当前提交哈希
    # 例如: https://github.com/PX4/PX4-Autopilot/blob/597da76221294b0d9b78fb908e12e71a376322f0/src%2Fmodules%2Fnavigator%2Frtl.cpp
    match = re.search(r'github\.com/([^/]+)/([^/]+)/blob/([^/]+)/(.+)$', blob_url)
    if not match:
        print(f"无法从URL解析仓库信息: {blob_url}")
        return None, None
        
    owner = match.group(1)
    repo_name = match.group(2)
    current_commit = match.group(3)
    
    # 获取前一个提交信息
    api_url = f"https://api.github.com/repos/{owner}/{repo_name}/commits/{current_commit}"
    
    # GitHub访问令牌
    headers = {
        "Authorization": os.getenv("GITHUB_AUTHORIZATION"),
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "GitHub-API-Client"
    }
    
    try:
        response = requests.get(api_url, headers=headers)
        
        if response.status_code != 200:
            print(f"获取提交信息失败，状态码: {response.status_code}")
            print(f"错误信息: {response.text}")
            return None, None
            
        # 解析响应，直接获取父提交信息
        commit_data = response.json()
        parents = commit_data.get("parents", [])
        if not parents:
            print(f"提交 {current_commit} 没有父提交")
            return None, None
            
        # 获取父提交的SHA和URL
        previous_commit = parents[0]["sha"]
        previous_url = parents[0]["url"]  # 直接使用API提供的URL
        
        return previous_commit, previous_url
        
    except Exception as e:
        print(f"获取前一个提交信息时出错: {str(e)}")
        return None, None

def download_file_from_commit(commit_url, file_path):
    """
    使用提交URL下载特定文件内容
    
    Args:
        commit_url: 提交的API URL
        file_path: 文件路径
        
    Returns:
        文件内容
    """
    # GitHub访问令牌
    headers = {
        "Authorization": os.getenv("GITHUB_AUTHORIZATION"),
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "GitHub-API-Client"
    }
    
    try:
        # 从commit_url获取仓库信息
        response = requests.get(commit_url, headers=headers)
        if response.status_code != 200:
            print(f"获取提交信息失败，状态码: {response.status_code}")
            return None
            
        commit_data = response.json()
        # 构建raw内容URL
        repo_url = commit_data.get("html_url", "")
        if not repo_url:
            print("未找到仓库URL")
            return None
            
        # 从HTML URL提取仓库信息和提交SHA
        # 例如: https://github.com/PX4/PX4-Autopilot/commit/e5503480e3a025728f760d0dcd05dd2a450b33a9
        match = re.search(r'github\.com/([^/]+)/([^/]+)/commit/([^/]+)$', repo_url)
        if not match:
            print(f"无法从URL解析仓库信息: {repo_url}")
            return None
            
        owner = match.group(1)
        repo = match.group(2)
        commit_sha = match.group(3)
        
        # 构建文件内容的API URL
        file_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{file_path}?ref={commit_sha}"
        raw_headers = {
            "Authorization": os.getenv("GITHUB_AUTHORIZATION"),
            "Accept": "application/vnd.github.v3.raw",
            "User-Agent": "GitHub-API-Client"
        }
        
        # 获取文件内容
        file_response = requests.get(file_url, headers=raw_headers)
        if file_response.status_code != 200:
            # 尝试直接从raw链接获取
            raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{commit_sha}/{file_path}"
            file_response = requests.get(raw_url, headers=raw_headers)
            
            if file_response.status_code != 200:
                print(f"获取文件内容失败，状态码: {file_response.status_code}")
                return None
                
        # 添加日志验证
        print(f"正在下载提交 {commit_sha} 中的文件 {file_path}")
        
        if file_response.status_code == 200:
            print(f"成功下载提交 {commit_sha} 中的文件 {file_path}")
            
        return file_response.text
        
    except Exception as e:
        print(f"下载文件内容时出错: {str(e)}")
        return None

def extract_cpp_function(content, function_name):
    if not content:
        return None

    try:
        # 确定函数前缀模式，处理类方法和普通函数
        if "::" in function_name:
            class_name, method_name = function_name.split("::", 1)
            header_pattern = re.escape(class_name) + r'::\s*' + re.escape(method_name) + r'\s*\('
        else:
            header_pattern = r'(?:[\w\s\*&]+\s+)?' + re.escape(function_name) + r'\s*\('  # 更精确地匹配函数签名

        # 找到函数头
        header_match = re.search(header_pattern, content)
        if not header_match:
            return None

        # 向前搜索找到函数签名的开始
        start = header_match.start()
        # 搜索函数签名开始 - 查找前面的返回类型和空白字符
        line_start = content.rfind('\n', 0, start)
        if line_start == -1:
            line_start = 0
        else:
            line_start += 1  # 跳过换行符

        # 从函数头部向后查找函数体的开始和结束
        brace_start = content.find('{', start)
        if brace_start == -1:
            return None

        # 使用栈匹配 {}
        count = 0
        for i in range(brace_start, len(content)):
            if content[i] == '{':
                count += 1
            elif content[i] == '}':
                count -= 1
                if count == 0:
                    return content[line_start:i+1].strip()  # 包含完整函数定义

        return None  # 如果函数体未闭合，返回None
    except Exception as e:
        print(f"提取函数定义时出错: {str(e)}")
        return None

def process_pr(pr, existing_functions=None):
    """
    处理单个PR，提取修改的函数在之前版本中的定义
    
    Args:
        pr: PR数据对象
        existing_functions: 已存在的函数定义字典
        
    Returns:
        {函数名: 函数定义} 字典
    """
    pr_number = pr.get('number')
    print(f"\n处理PR #{pr_number}: {pr.get('title', '')}")
    
    # 检查是否有modified_functions字段
    if 'modified_functions' not in pr:
        print(f"PR #{pr_number} 没有modified_functions字段")
        return {}
        
    modified_functions = pr.get('modified_functions', {})
    all_functions = modified_functions.get('all', [])
    by_file = modified_functions.get('by_file', {})
    
    if not all_functions:
        print(f"PR #{pr_number} 没有修改的函数")
        return {}
        
    print(f"PR #{pr_number} 有 {len(all_functions)} 个修改的函数")
    
    # 检查patches字段，用于获取文件URL和提交哈希
    patches = pr.get('patches', {})
    if not patches:
        print(f"PR #{pr_number} 没有patches字段")
        return {}
        
    result = {}
    
    # 收集函数到文件的映射
    function_file_map = {}
    for file_path, functions in by_file.items():
        for function in functions:
            function_file_map[function] = file_path
    
    existing_functions = existing_functions or {}
    pr_existing = existing_functions.get(str(pr_number), {})
    
    # 处理每个函数
    for function_name in all_functions:
        # 检查函数是否已存在于existing_functions中
        if function_name in pr_existing:
            print(f"函数 {function_name} 已存在于现有数据中，跳过处理")
            result[function_name] = pr_existing[function_name]
            continue
            
        file_path = function_file_map.get(function_name)
        if not file_path:
            print(f"未找到函数 {function_name} 对应的文件")
            continue
            
        # 获取patch信息
        patch_info = patches.get(file_path)
        if not patch_info:
            print(f"未找到文件 {file_path} 的patch信息")
            continue
            
        # 获取blob_url
        blob_url = patch_info.get('blob_url')
        if not blob_url:
            print(f"未找到文件 {file_path} 的blob_url")
            continue
            
        # 获取前一个提交信息
        previous_commit, previous_url = get_previous_commit_info(blob_url)
        if not previous_commit or not previous_url:
            print(f"未找到当前提交的前一个提交信息")
            continue
        
        # 从blob_url中提取文件路径
        match = re.search(r'github\.com/([^/]+)/([^/]+)/blob/([^/]+)/(.+)$', blob_url)
        if not match:
            print(f"无法从URL解析仓库信息: {blob_url}")
            continue
            
        file_path_url = match.group(4)
        repo = "PX4/PX4-Autopilot"
        
        # URL解码文件路径
        import urllib.parse
        file_path = urllib.parse.unquote(file_path_url)
        
        # 下载前一个版本的文件内容
        print(f"下载 {file_path} 的前一个版本 ({previous_commit})")
        content = download_file_from_commit(previous_url, file_path)
        if not content:
            print(f"无法获取文件 {file_path} 在提交 {previous_commit} 的内容")
            continue
            
        # 提取函数定义
        print(f"提取函数 {function_name} 的定义")
        function_def = extract_cpp_function(content, function_name)
        if function_def:
            result[function_name] = {
                "file": file_path,
                "commit": previous_commit,
                "source": function_def
            }
            print(f"成功提取函数 {function_name}")
        else:
            print(f"未能提取函数 {function_name} 的定义")
    
    return result

def process_all_prs(pr_data, output_file="previous_functions.json", thread_count=5):
    """
    处理所有PR
    
    Args:
        pr_data: PR数据列表
        output_file: 输出文件路径
        thread_count: 线程数量
        
    Returns:
        处理结果字典
    """
    total = len(pr_data)
    print(f"开始处理 {total} 个PR，使用 {thread_count} 个线程")
    
    # 加载已有的函数定义
    existing_functions = load_json_file(output_file)
    
    results = existing_functions.copy()
    results_lock = threading.Lock()  # 用于同步结果字典的锁
    processed_count = 0
    processed_lock = threading.Lock()  # 用于同步计数的锁
    
    def process_pr_thread(pr):
        """线程函数，处理单个PR并更新结果"""
        nonlocal processed_count
        pr_number = str(pr.get('number'))
        
        # 调用process_pr函数，传入已存在的函数定义
        pr_result = process_pr(pr, existing_functions)
        
        if pr_result:
            # 使用锁保护结果字典的更新
            with results_lock:
                results[pr_number] = pr_result
        
        # 更新处理计数并保存中间结果
        with processed_lock:
            processed_count += 1
            current_count = processed_count
            
            # 每处理完5个PR，保存一次中间结果
            if current_count % 5 == 0:
                with results_lock:  # 确保在保存时没有其他线程在修改结果
                    save_json_file(results, f"{output_file}.temp")
                print(f"已处理 {current_count}/{total} 个PR")
    
    # 创建线程池
    with ThreadPoolExecutor(max_workers=thread_count) as executor:
        # 提交所有PR到线程池
        futures = [executor.submit(process_pr_thread, pr) for pr in pr_data]
        
        # 等待所有任务完成
        for future in futures:
            future.result()
    
    # 保存最终结果
    save_json_file(results, output_file)
    print(f"所有PR处理完成，共处理 {len(results)} 个PR")
    return results

def main():
    # 记录开始时间
    start_time = time.time()
    print(f"开始运行时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 加载PR数据
    input_file = "px4_navigator_prs.json"
    output_file = "previous_functions.json"
    thread_count = 5  # 使用5个线程
    
    pr_data = load_json_file(input_file)
    if not pr_data:
        return
    
    # 处理所有PR，使用多线程并进行增量更新
    process_all_prs(pr_data, output_file, thread_count)
    
    # 记录结束时间
    end_time = time.time()
    elapsed_time = end_time - start_time
    hours, remainder = divmod(elapsed_time, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    print(f"结束运行时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"总耗时: {int(hours)}小时 {int(minutes)}分钟 {seconds:.2f}秒")

if __name__ == "__main__":
    main()

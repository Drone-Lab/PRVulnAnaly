import os
import requests
import json
import re
import time
import datetime
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
        print(f"成功加载JSON文件，共有 {len(data)} 个PR记录")
        return data
    except Exception as e:
        print(f"加载JSON文件失败: {str(e)}")
        return None

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
                
        return file_response.text
        
    except Exception as e:
        print(f"下载文件内容时出错: {str(e)}")
        return None

def extract_cpp_function(content, function_name):
    """
    从C++文件内容中提取指定函数的完整定义
    
    Args:
        content: 文件内容
        function_name: 要提取的函数名，格式为 "类名::函数名" 或 "函数名"
        
    Returns:
        函数定义字符串
    """
    if not content:
        return None
        
    try:
        if "::" in function_name:
            # 处理类方法
            class_name, method_name = function_name.split("::", 1)
            # 匹配函数定义: 任何返回类型 + 类名::函数名 + 参数 + 函数体
            pattern = r'(?:virtual|static|inline)?\s*[\w:<>\s\*&]+\s+' + re.escape(class_name) + r'::\s*' + re.escape(method_name) + r'\s*\([^\)]*\)(?:\s*const)?\s*(?:override|final)?\s*\{(?:[^{}]*|\{(?:[^{}]*|\{[^{}]*\})*\})*\}'
        else:
            # 处理普通函数
            pattern = r'(?:static|inline)?\s*[\w:<>\s\*&]+\s+' + re.escape(function_name) + r'\s*\([^\)]*\)(?:\s*const)?\s*\{(?:[^{}]*|\{(?:[^{}]*|\{[^{}]*\})*\})*\}'
            
        match = re.search(pattern, content, re.DOTALL)
        if match:
            return match.group(0).strip()
            
        # 尝试查找函数声明
        declaration_pattern = r'(?:virtual|static|inline)?\s*[\w:<>\s\*&]+\s+' + re.escape(function_name) + r'\s*\([^\)]*\)(?:\s*const)?(?:\s*override|final)?;'
        match = re.search(declaration_pattern, content, re.DOTALL)
        if match:
            return match.group(0).strip() + " // 仅函数声明，未找到定义"
            
        return None
    except Exception as e:
        print(f"提取函数定义时出错: {str(e)}")
        return None

def process_pr(pr):
    """
    处理单个PR，提取修改的函数在之前版本中的定义
    
    Args:
        pr: PR数据对象
        
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
    
    # 处理每个函数
    for function_name in all_functions:
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

def process_all_prs(pr_data, output_file="previous_functions.json"):
    """
    处理所有PR
    
    Args:
        pr_data: PR数据列表
        output_file: 输出文件路径
        
    Returns:
        处理结果字典
    """
    total = len(pr_data)
    print(f"开始处理 {total} 个PR")
    
    results = {}
    
    for i, pr in enumerate(pr_data):
        pr_number = str(pr.get('number'))
        pr_result = process_pr(pr)
        if pr_result:
            results[pr_number] = pr_result
            
        # 每处理完10个PR，保存一次中间结果
        if (i + 1) % 10 == 0:
            save_json_file(results, f"{output_file}.temp")
            print(f"已处理 {i + 1}/{total} 个PR")
    
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
    
    pr_data = load_json_file(input_file)
    if not pr_data:
        return
    
    # 处理所有PR
    process_all_prs(pr_data, output_file)
    
    # 记录结束时间
    end_time = time.time()
    elapsed_time = end_time - start_time
    hours, remainder = divmod(elapsed_time, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    print(f"结束运行时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"总耗时: {int(hours)}小时 {int(minutes)}分钟 {seconds:.2f}秒")

if __name__ == "__main__":
    main()

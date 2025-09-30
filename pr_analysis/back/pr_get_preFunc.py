import os
import requests
import json
import re
import time
import datetime
import threading
import shutil
import pathlib
from concurrent.futures import ThreadPoolExecutor

def ensure_dir_exists(directory):
    """
    确保目录存在，如果不存在则创建
    
    Args:
        directory: 目录路径
    """
    if not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)
        print(f"创建目录: {directory}")
    return directory

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
        (current_commit, previous_commit, previous_url): 当前提交哈希, 前一个提交哈希和API URL
    """
    # 从blob_url中提取当前提交哈希
    # 例如: https://github.com/PX4/PX4-Autopilot/blob/597da76221294b0d9b78fb908e12e71a376322f0/src%2Fmodules%2Fnavigator%2Frtl.cpp
    match = re.search(r'github\.com/([^/]+)/([^/]+)/blob/([^/]+)/(.+)$', blob_url)
    if not match:
        print(f"无法从URL解析仓库信息: {blob_url}")
        return None, None, None
        
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
            return None, None, None
            
        # 解析响应，直接获取父提交信息
        commit_data = response.json()
        parents = commit_data.get("parents", [])
        if not parents:
            print(f"提交 {current_commit} 没有父提交")
            return current_commit, None, None
            
        # 获取父提交的SHA和URL
        previous_commit = parents[0]["sha"]
        previous_url = parents[0]["url"]  # 直接使用API提供的URL
        
        return current_commit, previous_commit, previous_url
        
    except Exception as e:
        print(f"获取前一个提交信息时出错: {str(e)}")
        return None, None, None

def download_file_from_commit(commit_url, file_path, save_dir=None):
    """
    使用提交URL下载特定文件内容，并可选地保存到本地文件系统
    
    Args:
        commit_url: 提交的API URL
        file_path: 文件路径
        save_dir: 保存文件的目录路径，如果提供则保存文件
        
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
        
        content = file_response.text
        
        # 如果提供了保存目录，则保存文件
        if save_dir and content:
            # 确保目录存在
            ensure_dir_exists(save_dir)
            
            # 处理文件名，去除不合法字符
            file_name = os.path.basename(file_path)
            safe_file_name = re.sub(r'[<>:"/\\|?*]', '_', file_name)  # 替换Windows不允许的文件名字符
            
            # 构建完整的保存路径
            save_path = os.path.join(save_dir, safe_file_name)
            
            # 如果文件名相同但内容不同，添加后缀
            counter = 1
            original_save_path = save_path
            while os.path.exists(save_path):
                # 检查内容是否相同
                with open(save_path, 'r', encoding='utf-8', errors='ignore') as f:
                    existing_content = f.read()
                if existing_content == content:
                    break  # 内容相同，不需要创建新文件
                # 内容不同，创建带编号的新文件名
                name, ext = os.path.splitext(original_save_path)
                save_path = f"{name}_{counter}{ext}"
                counter += 1
            
            # 保存文件
            try:
                with open(save_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                print(f"文件已保存到: {save_path}")
            except Exception as e:
                print(f"保存文件时出错: {str(e)}")
        
        if file_response.status_code == 200:
            print(f"成功下载提交 {commit_sha} 中的文件 {file_path}")
            
        return content
        
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

def process_pr(pr, existing_functions=None, save_files=True, base_save_dir="downloaded_files"):
    """
    处理单个PR，提取修改的函数在之前版本中的定义
    
    Args:
        pr: PR数据对象
        existing_functions: 已存在的函数定义字典
        save_files: 是否保存文件到本地
        base_save_dir: 基础保存目录
        
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
    
    # 如果启用了文件保存，创建PR对应的保存目录
    pr_save_dir = None
    if save_files:
        pr_save_dir = os.path.join(base_save_dir, f"pr_{pr_number}")
        ensure_dir_exists(pr_save_dir)
    
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
        current_commit, previous_commit, previous_url = get_previous_commit_info(blob_url)
        if not current_commit or not previous_commit or not previous_url:
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
        
        # 如果启用了文件保存，创建函数相关的保存目录
        func_save_dir = None
        if save_files and pr_save_dir:
            # 创建一个安全的函数名作为目录名
            safe_func_name = re.sub(r'[<>:"/\\|?*]', '_', function_name)
            func_save_dir = os.path.join(pr_save_dir, safe_func_name)
            ensure_dir_exists(func_save_dir)
        
        # 下载并可选保存文件
        content = download_file_from_commit(previous_url, file_path, func_save_dir)
        if not content:
            print(f"无法获取文件 {file_path} 在提交 {previous_commit} 的内容")
            continue
            
        # 提取函数定义
        print(f"提取函数 {function_name} 的定义")
        function_def = extract_cpp_function(content, function_name)
        if function_def:
            result[function_name] = {
                "file": file_path,
                "current_commit": current_commit,  # 当前提交哈希（修改后的代码）
                "previous_commit": previous_commit,  # 父提交哈希（修改前的代码）
                "source": function_def
            }
            
            # 如果启用了文件保存，将提取的函数定义也保存到文件中
            if save_files and func_save_dir:
                func_def_file = os.path.join(func_save_dir, "function_def.txt")
                try:
                    with open(func_def_file, 'w', encoding='utf-8') as f:
                        f.write(function_def)
                    print(f"函数定义已保存到: {func_def_file}")
                except Exception as e:
                    print(f"保存函数定义时出错: {str(e)}")
            
            print(f"成功提取函数 {function_name}")
        else:
            print(f"未能提取函数 {function_name} 的定义")
    
    return result

def process_all_prs(pr_data, output_file="previous_functions.json", thread_count=5, save_files=True, base_save_dir="downloaded_files"):
    """
    处理所有PR
    
    Args:
        pr_data: PR数据列表
        output_file: 输出文件路径
        thread_count: 线程数量
        save_files: 是否保存文件到本地
        base_save_dir: 基础保存目录
        
    Returns:
        处理结果字典
    """
    total = len(pr_data)
    print(f"开始处理 {total} 个PR，使用 {thread_count} 个线程")
    
    # 如果启用了文件保存，确保基础目录存在
    if save_files:
        ensure_dir_exists(base_save_dir)
    
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
        
        # 调用process_pr函数，传入已存在的函数定义和文件保存选项
        pr_result = process_pr(pr, existing_functions, save_files, base_save_dir)
        
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

def query_single_pr(pr_number, pr_data_file="px4_navigator_prs.json", output_file="previous_functions.json", save_files=True, base_save_dir="downloaded_files"):
    """
    查询并处理单个PR
    
    Args:
        pr_number: PR编号
        pr_data_file: PR数据文件路径
        output_file: 输出文件路径
        save_files: 是否保存文件到本地
        base_save_dir: 基础保存目录
        
    Returns:
        处理结果，如果PR不存在则返回None
    """
    # 加载PR数据和已有函数定义
    pr_data = load_json_file(pr_data_file)
    existing_functions = load_json_file(output_file)
    
    if not pr_data:
        print("无法加载PR数据，请检查文件路径")
        return None
    
    # 查找指定编号的PR
    target_pr = None
    for pr in pr_data:
        if str(pr.get('number')) == str(pr_number):
            target_pr = pr
            break
    
    if not target_pr:
        print(f"未找到PR #{pr_number}")
        return None
    
    print(f"找到PR #{pr_number}: {target_pr.get('title', '')}")
    
    # 处理指定的PR
    result = process_pr(target_pr, existing_functions, save_files, base_save_dir)
    
    if not result:
        print(f"处理PR #{pr_number} 未找到函数定义")
        return None
    
    # 更新结果并保存
    if existing_functions.get(str(pr_number)) != result:
        existing_functions[str(pr_number)] = result
        save_json_file(existing_functions, output_file)
    
    return result

def interactive_query():
    """
    交互式查询单个PR
    """
    print("\n===== PR函数查询工具 =====")
    
    while True:
        pr_number = input("\n请输入要查询的PR编号 (输入'q'退出): ").strip()
        
        if pr_number.lower() == 'q':
            print("退出查询模式")
            break
        
        # 验证输入是否为有效的PR编号（数字）
        if not pr_number.isdigit():
            print("请输入有效的PR编号（数字）")
            continue
        
        # 查询PR
        result = query_single_pr(pr_number)
        
        if result:
            # 显示查询结果摘要
            print(f"\nPR #{pr_number} 查询结果:")
            print(f"找到 {len(result)} 个函数定义")
            
            # 函数列表，用于后续展示完整内容
            functions = list(result.items())
            
            for i, (func_name, func_info) in enumerate(functions, 1):
                print(f"\n{i}. 函数: {func_name}")
                print(f"   文件: {func_info.get('file', '未知')}")
                print(f"   当前提交: {func_info.get('current_commit', '未知')}")
                print(f"   前一个提交: {func_info.get('previous_commit', '未知')}")
                
                # 显示函数定义的前几行
                source = func_info.get('source', '')
                preview_lines = source.split('\n')[:3]
                preview = '\n'.join(preview_lines)
                if len(preview_lines) < len(source.split('\n')):
                    preview += "\n... (更多行)"
                    
                print(f"   函数定义预览:\n{preview}")
                
                # 如果保存了文件，显示路径
                func_file_path = f"downloaded_files/pr_{pr_number}/{func_name.replace('::', '_')}/function_def.txt"
                if os.path.exists(func_file_path):
                    print(f"   函数定义已保存到: {func_file_path}")
            
            # 提供查看完整函数定义的选项
            while len(functions) > 0:
                view_choice = input("\n输入函数编号查看完整定义，或输入'b'返回: ").strip().lower()
                
                if view_choice == 'b':
                    break
                
                try:
                    idx = int(view_choice) - 1
                    if 0 <= idx < len(functions):
                        func_name, func_info = functions[idx]
                        print(f"\n===== 函数: {func_name} =====")
                        print(f"文件: {func_info.get('file', '未知')}")
                        print(f"当前提交: {func_info.get('current_commit', '未知')}")
                        print(f"前一个提交: {func_info.get('previous_commit', '未知')}")
                        print(f"\n函数完整定义:\n{func_info.get('source', '无可用内容')}")
                    else:
                        print("无效的函数编号")
                except ValueError:
                    print("请输入有效的数字或'b'")
        
        # 询问是否继续查询其他PR
        choice = input("\n是否继续查询其他PR？ (y/n): ").strip().lower()
        if choice != 'y':
            print("退出查询模式")
            break

def main():
    # 记录开始时间
    start_time = time.time()
    print(f"开始运行时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 询问用户选择批量处理还是单一PR查询
    print("\n请选择操作模式:")
    print("1. 批量处理所有PR")
    print("2. 交互式查询单个PR")
    
    choice = input("请选择 (1/2): ").strip()
    
    if choice == '2':
        # 单一PR查询模式
        interactive_query()
    else:
        # 默认批量处理模式
        # 加载PR数据
        input_file = "px4_navigator_prs.json"
        output_file = "previous_functions.json"
        thread_count = 5  # 使用5个线程
        save_files = True  # 启用文件保存
        base_save_dir = "downloaded_files"  # 基础保存目录
        
        pr_data = load_json_file(input_file)
        if not pr_data:
            return
        
        # 处理所有PR，使用多线程并进行增量更新，保存文件到本地
        process_all_prs(pr_data, output_file, thread_count, save_files, base_save_dir)
    
    # 记录结束时间
    end_time = time.time()
    elapsed_time = end_time - start_time
    hours, remainder = divmod(elapsed_time, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    print(f"结束运行时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"总耗时: {int(hours)}小时 {int(minutes)}分钟 {seconds:.2f}秒")

if __name__ == "__main__":
    main()

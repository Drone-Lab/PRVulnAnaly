import os
import requests
import urllib.parse
import re
import json
import time
from concurrent.futures import ThreadPoolExecutor
'''
文件作用：解析指定json文件中的所有updateUsecase_patches，获取对应版本和前一个版本的完整函数体
'''
def parse_github_url(url):
    """
    解析GitHub URL，提取仓库名、提交哈希和文件路径
    """
    # 处理raw.githubusercontent.com和github.com/raw两种格式
    if "raw.githubusercontent.com" in url:
        # 格式: https://raw.githubusercontent.com/ArduPilot/ardupilot/c5e12ebb6838487a7a6d7eb09519b4301a763215/Tools/autotest/arduplane.py
        pattern = r"https://raw\.githubusercontent\.com/([^/]+)/([^/]+)/([^/]+)/(.*)"
        match = re.match(pattern, url)
        if match:
            owner, repo, commit_hash, file_path = match.groups()
    else:
        # 格式: https://github.com/ArduPilot/ardupilot/raw/c5e12ebb6838487a7a6d7eb09519b4301a763215/Tools%2Fautotest%2Farduplane.py
        pattern = r"https://github\.com/([^/]+)/([^/]+)/raw/([^/]+)/(.*)"
        match = re.match(pattern, url)
        if match:
            owner, repo, commit_hash, file_path = match.groups()
            # URL解码文件路径
            file_path = urllib.parse.unquote(file_path)
    
    if not match:
        raise ValueError("无法解析GitHub URL，请确保URL格式正确")
    
    return {
        "owner": owner,
        "repo": repo,
        "commit_hash": commit_hash,
        "file_path": file_path
    }

def get_previous_commit_hash(owner, repo, commit_hash):
    """
    获取给定提交的上一个提交哈希值
    
    参数:
        owner: 仓库所有者
        repo: 仓库名称
        commit_hash: 当前提交哈希值
        
    返回:
        上一个提交的哈希值，如果获取失败则返回None
    """
    try:
        # 构建API请求URL获取当前提交信息
        api_url = f"https://api.github.com/repos/{owner}/{repo}/commits/{commit_hash}"
        
        # GitHub访问令牌
        headers = {
            "Authorization": os.getenv("GITHUB_AUTHORIZATION"),
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "GitHub-File-Downloader"
        }
        
        print(f"正在获取提交 {commit_hash} 的信息...")
        response = requests.get(api_url, headers=headers)
        
        if response.status_code != 200:
            print(f"获取提交信息失败，状态码: {response.status_code}")
            print(f"错误信息: {response.text}")
            return None
            
        # 解析响应
        commit_data = response.json()
        
        # 获取父提交
        parents = commit_data.get("parents", [])
        if not parents:
            print(f"提交 {commit_hash} 没有父提交（可能是初始提交）")
            return None
            
        # 返回第一个父提交的哈希值
        previous_hash = parents[0]["sha"]
        print(f"找到上一个提交: {previous_hash}")
        return previous_hash
        
    except Exception as e:
        print(f"获取上一个提交哈希值时出错: {str(e)}")
        return None

def download_github_file(url, output_dir="./downloaded_files"):
    """
    从GitHub下载特定版本的文件并保存为txt
    """
    print(f"正在处理链接: {url}")
    
    try:
        # 解析URL
        repo_info = parse_github_url(url)
        owner = repo_info["owner"]
        repo = repo_info["repo"]
        commit_hash = repo_info["commit_hash"]
        file_path = repo_info["file_path"]
        
        print(f"仓库: {owner}/{repo}")
        print(f"提交哈希: {commit_hash}")
        print(f"文件路径: {file_path}")
        
        # 构建API请求
        api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{file_path}?ref={commit_hash}"
        
        # GitHub访问令牌
        headers = {
            "Authorization": os.getenv("GITHUB_AUTHORIZATION"),
            "Accept": "application/vnd.github.v3.raw",
            "User-Agent": "GitHub-File-Downloader"
        }
        
        print(f"正在请求文件内容...")
        response = requests.get(api_url, headers=headers)
        
        # 检查响应状态
        if response.status_code != 200:
            # 尝试直接从raw链接获取
            raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{commit_hash}/{file_path}"
            print(f"API请求失败，尝试从raw链接获取: {raw_url}")
            response = requests.get(raw_url, headers=headers)
            
            if response.status_code != 200:
                print(f"获取文件失败，状态码: {response.status_code}")
                print(f"错误信息: {response.text}")
                return False
        
        # 创建输出目录
        os.makedirs(output_dir, exist_ok=True)
        
        # 生成输出文件名
        file_name = os.path.basename(file_path)
        output_file = os.path.join(output_dir, f"{file_name}_{commit_hash[:8]}.txt")
        
        # 保存文件内容
        with open(output_file, "wb") as f:
            f.write(response.content)
        
        print(f"文件已成功下载并保存到: {output_file}")
        return output_file
    
    except Exception as e:
        print(f"下载过程中出错: {str(e)}")
        return False

def find_function_in_file(file_path, function_name):
    """
    在文件中查找指定函数名的完整函数定义
    
    参数:
        file_path: 文件路径
        function_name: 要查找的函数名
        
    返回:
        找到的函数定义字符串，未找到则返回None
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # 用于匹配Python函数定义的正则表达式
        # 匹配 def function_name(参数列表): 开始的函数定义
        function_pattern = rf'def\s+{re.escape(function_name)}\s*\([^)]*\)(?:\s*->.*?)?:'
        
        match = re.search(function_pattern, content)
        if not match:
            print(f"在文件中未找到函数 '{function_name}'")
            return None
            
        # 找到函数定义的起始位置
        start_pos = match.start()
        
        # 获取整个文件内容的行列表
        lines = content.split('\n')
        
        # 计算函数定义开始的行号
        start_line = content[:start_pos].count('\n')
        
        # 获取函数定义所在行的缩进级别
        def_line = lines[start_line]
        indent_match = re.match(r'^(\s*)', def_line)
        base_indent = indent_match.group(1) if indent_match else ''
        base_indent_len = len(base_indent)
        
        # 收集函数体
        function_lines = [def_line]
        current_line = start_line + 1
        
        # 收集具有相同或更深缩进级别的行，直到遇到缩进级别低于函数定义的行
        while current_line < len(lines):
            line = lines[current_line]
            
            # 跳过空行
            if not line.strip():
                function_lines.append(line)
                current_line += 1
                continue
                
            # 检查缩进级别
            indent_match = re.match(r'^(\s*)', line)
            indent = indent_match.group(1) if indent_match else ''
            
            # 如果缩进级别小于或等于函数定义的缩进级别，则说明函数体已结束
            if len(indent) <= base_indent_len and current_line > start_line + 1:
                break
            
            function_lines.append(line)
            current_line += 1
        
        # 将收集到的函数体行合并为一个字符串
        function_code = '\n'.join(function_lines)
        return function_code
        
    except Exception as e:
        print(f"查找函数时出错: {str(e)}")
        return None

def get_function_from_previous_version(url, function_name):
    """
    获取特定函数在当前提交版本的上一个版本中的代码
    
    参数:
        url: GitHub文件URL
        function_name: 要查找的函数名
        
    返回:
        字典，包含当前版本和上一版本的函数代码，获取失败则相应的值为None
    """
    result = {
        "current_version": None,
        "previous_version": None,
        "current_commit": None,
        "previous_commit": None
    }
    
    try:
        # 解析URL获取仓库信息
        repo_info = parse_github_url(url)
        owner = repo_info["owner"]
        repo = repo_info["repo"]
        commit_hash = repo_info["commit_hash"]
        file_path = repo_info["file_path"]
        
        # 记录当前提交哈希
        result["current_commit"] = commit_hash
        
        # 下载当前版本文件
        current_file = download_github_file(url)
        if current_file:
            # 提取当前版本的函数
            current_function = find_function_in_file(current_file, function_name)
            result["current_version"] = current_function
        
        # 获取上一个提交的哈希值
        previous_hash = get_previous_commit_hash(owner, repo, commit_hash)
        if not previous_hash:
            print(f"无法获取上一个提交哈希值")
            return result
            
        # 记录上一个提交哈希
        result["previous_commit"] = previous_hash
        
        # 构建上一个版本的URL
        previous_url = url.replace(commit_hash, previous_hash)
        print(f"上一版本URL: {previous_url}")
        
        # 下载上一个版本的文件
        previous_file = download_github_file(previous_url)
        if previous_file:
            # 提取上一个版本的函数
            previous_function = find_function_in_file(previous_file, function_name)
            result["previous_version"] = previous_function
            
        return result
        
    except Exception as e:
        print(f"获取函数上一版本时出错: {str(e)}")
        return result

def extract_function_from_url(url, function_name):
    """
    从GitHub URL下载文件并提取指定函数
    
    参数:
        url: GitHub文件URL
        function_name: 要提取的函数名
    
    返回:
        函数代码字符串，如果下载失败或函数未找到则返回None
    """
    # 下载文件
    file_path = download_github_file(url)
    if not file_path:
        return None
    
    # 在文件中查找函数
    print(f"在文件中查找函数 '{function_name}'...")
    function_code = find_function_in_file(file_path, function_name)
    
    if function_code:
        print(f"已找到函数 '{function_name}'")
        # 将找到的函数另存为单独的文件
        output_dir = os.path.dirname(file_path)
        function_file = os.path.join(output_dir, f"{function_name}.txt")
        
        with open(function_file, 'w', encoding='utf-8') as f:
            f.write(function_code)
        
        print(f"函数已保存到: {function_file}")
        return function_code
    else:
        print(f"未在文件中找到函数 '{function_name}'")
        return None

def process_pr_json(json_file_path, output_file_path="extracted_functions.json", max_workers=5, start_index=0, batch_size=None, extract_previous_version=False):
    """
    处理PR JSON文件，提取所有相关函数定义，支持增量更新
    
    参数:
        json_file_path: PR JSON文件路径
        output_file_path: 输出JSON文件路径
        max_workers: 最大线程数
        start_index: 处理的起始索引
        batch_size: 批处理大小，None表示处理所有
        extract_previous_version: 是否提取函数的上一个版本
        
    返回:
        提取的函数定义字典
    """
    print(f"开始处理PR JSON文件: {json_file_path}")
    
    try:
        # 读取JSON文件
        with open(json_file_path, 'r', encoding='utf-8') as f:
            pr_data = json.load(f)
        
        # 如果输出文件已存在，先加载已有内容进行增量更新
        extracted_functions = {}
        if os.path.exists(output_file_path):
            try:
                with open(output_file_path, 'r', encoding='utf-8') as f:
                    extracted_functions = json.load(f)
                print(f"加载已有输出文件，包含 {len(extracted_functions)} 个PR的函数定义")
            except Exception as e:
                print(f"加载已有输出文件时出错: {str(e)}")
                print("将创建新的输出文件")
        
        # 用于存储下载的文件缓存，避免重复下载
        file_cache = {}
        
        # 获取要处理的PR列表
        pr_items = list(pr_data.items())
        pr_count = len(pr_items)
        print(f"找到 {pr_count} 个PR记录")
        
        # 计算处理范围
        end_index = min(start_index + batch_size, pr_count) if batch_size else pr_count
        pr_to_process = pr_items[start_index:end_index]
        print(f"本次处理 {len(pr_to_process)} 个PR记录，从索引 {start_index} 到 {end_index-1}")
        
        # 创建线程池
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 遍历PR
            for pr_number, pr_info in pr_to_process:
                print(f"\n处理PR #{pr_number}: {pr_info.get('title', '')}")
                
                # 获取ardu_changes字段
                ardu_changes = pr_info.get('ardu_changes', {})
                if not ardu_changes:
                    print(f"PR #{pr_number} 没有代码变更")
                    continue
                
                # 遍历每个文件的变更
                for file_path, file_info in ardu_changes.items():
                    print(f"处理文件: {file_path}")
                    
                    # 获取raw_url
                    raw_url = file_info.get('raw_url')
                    if not raw_url:
                        print(f"文件 {file_path} 没有raw_url，跳过")
                        continue
                    
                    # 收集需要提取的函数名
                    functions_to_extract = []
                    
                    # 检查添加的用例补丁
                    for patch in file_info.get('addUsecase_patches', []):
                        function_name = patch.get('function_name')
                        if function_name:
                            functions_to_extract.append(function_name)
                    
                    # 检查更新的用例补丁
                    for patch in file_info.get('updateUsecase_patches', []):
                        function_name = patch.get('function_name')
                        if function_name:
                            functions_to_extract.append(function_name)
                    
                    # 去除重复的函数名
                    functions_to_extract = list(set(functions_to_extract))
                    
                    if not functions_to_extract:
                        print(f"文件 {file_path} 没有需要提取的函数")
                        continue
                    
                    # 为当前PR创建字典
                    if pr_number not in extracted_functions:
                        extracted_functions[pr_number] = {}
                    
                    # 处理每个函数
                    for function_name in functions_to_extract:
                        try:
                            if extract_previous_version:
                                # 提取当前版本和上一版本的函数
                                print(f"提取函数 '{function_name}' 的当前版本和上一版本...")
                                versions = get_function_from_previous_version(raw_url, function_name)
                                
                                if versions["current_version"]:
                                    print(f"成功提取函数 '{function_name}' 的当前版本")
                                    
                                    # 保存当前版本和上一版本的函数代码
                                    extracted_functions[pr_number][function_name] = {
                                        "current_version": {
                                            "code": versions["current_version"],
                                            "commit": versions["current_commit"]
                                        }
                                    }
                                    
                                    if versions["previous_version"]:
                                        print(f"成功提取函数 '{function_name}' 的上一版本")
                                        extracted_functions[pr_number][function_name]["previous_version"] = {
                                            "code": versions["previous_version"],
                                            "commit": versions["previous_commit"]
                                        }
                                    else:
                                        print(f"无法提取函数 '{function_name}' 的上一版本")
                                else:
                                    print(f"无法提取函数: {function_name}")
                            else:
                                # 仅提取当前版本的函数（如果尚未下载）
                                if raw_url not in file_cache:
                                    print(f"下载文件: {raw_url}")
                                    file_path = download_github_file(raw_url)
                                    if file_path:
                                        file_cache[raw_url] = file_path
                                    else:
                                        print(f"无法下载文件: {raw_url}")
                                        continue
                                else:
                                    print(f"使用缓存的文件: {file_cache[raw_url]}")
                                    file_path = file_cache[raw_url]
                                    
                                # 提取函数
                                function_code = find_function_in_file(file_path, function_name)
                                if function_code:
                                    print(f"成功提取函数: {function_name}")
                                    extracted_functions[pr_number][function_name] = function_code
                                else:
                                    print(f"无法提取函数: {function_name}")
                        except Exception as e:
                            print(f"提取函数 {function_name} 时发生错误: {str(e)}")
                
                # 每处理完一个PR，保存一次中间结果，防止中断丢失
                if (int(pr_number) % 10 == 0) or (pr_number == pr_to_process[-1][0]):
                    print(f"\n保存中间结果到: {output_file_path}")
                    with open(output_file_path, 'w', encoding='utf-8') as f:
                        json.dump(extracted_functions, f, ensure_ascii=False, indent=2)
        
        # 最终保存结果
        print(f"\n保存提取的函数到: {output_file_path}")
        with open(output_file_path, 'w', encoding='utf-8') as f:
            json.dump(extracted_functions, f, ensure_ascii=False, indent=2)
        
        print(f"处理完成，共从 {len(extracted_functions)} 个PR中提取了函数")
        return extracted_functions
        
    except Exception as e:
        print(f"处理PR JSON文件时出错: {str(e)}")
        return {}

def main():
    print("GitHub文件下载工具")
    
    # 选择操作模式
    print("\n选择操作模式:")
    print("1. 下载单个文件")
    print("2. 从文件中提取函数")
    print("3. 处理PR JSON文件")
    print("4. 提取函数前后版本")
    
    choice = input("请输入选择 (1-4): ")
    
    if choice == '1':
        # 下载单个文件
        url = input("请输入GitHub文件URL (或按回车使用示例URL): ")
        if not url:
            url = "https://github.com/ArduPilot/ardupilot/raw/c5e12ebb6838487a7a6d7eb09519b4301a763215/Tools%2Fautotest%2Farduplane.py"
            print(f"使用示例URL: {url}")
        
        output_file = download_github_file(url)
        if output_file:
            print(f"处理完成，文件已保存到: {output_file}")
        else:
            print("文件下载失败")
            
    elif choice == '2':
        # 提取函数
        url = input("请输入GitHub文件URL (或按回车使用示例URL): ")
        if not url:
            url = "https://github.com/ArduPilot/ardupilot/raw/c5e12ebb6838487a7a6d7eb09519b4301a763215/Tools%2Fautotest%2Farduplane.py"
            print(f"使用示例URL: {url}")
            
        function_name = input("请输入要提取的函数名: ")
        function_code = extract_function_from_url(url, function_name)
        if function_code:
            print("\n找到的函数代码:")
            print("-" * 50)
            print(function_code)
            print("-" * 50)
            
    elif choice == '3':
        # 处理PR JSON文件
        json_file = input("请输入PR JSON文件路径: ")
        if not json_file:
            json_file = "px4_navigator_prs.json"
            print(f"使用默认文件: {json_file}")
            
        output_file = input("请输入输出文件路径 (或按回车使用默认路径): ")
        if not output_file:
            output_file = "extracted_functions.json"
            print(f"使用默认输出文件: {output_file}")
        
        # 是否提取上一版本
        extract_previous = input("是否同时提取函数的上一版本? (y/n): ").lower() == 'y'
        
        # 增量更新设置    
        use_incremental = input("是否启用增量更新? (y/n): ").lower() == 'y'
        if use_incremental:
            start_index = input("请输入起始索引 (或按回车使用0): ")
            start_index = int(start_index) if start_index.isdigit() else 0
            
            batch_size = input("请输入批处理大小 (或按回车处理所有剩余PR): ")
            batch_size = int(batch_size) if batch_size.isdigit() else None
            
            print(f"将从索引 {start_index} 开始" + (f"处理 {batch_size} 个PR" if batch_size else "处理所有剩余PR"))
            process_pr_json(json_file, output_file, start_index=start_index, batch_size=batch_size, extract_previous_version=extract_previous)
        else:
            process_pr_json(json_file, output_file, extract_previous_version=extract_previous)
    
    elif choice == '4':
        # 提取函数前后版本
        url = input("请输入GitHub文件URL (或按回车使用示例URL): ")
        if not url:
            url = "https://github.com/ArduPilot/ardupilot/raw/c5e12ebb6838487a7a6d7eb09519b4301a763215/Tools%2Fautotest%2Farduplane.py"
            print(f"使用示例URL: {url}")
            
        function_name = input("请输入要提取的函数名: ")
        versions = get_function_from_previous_version(url, function_name)
        
        print("\n当前版本和上一版本的函数代码:")
        print("=" * 60)
        print(f"当前提交: {versions['current_commit']}")
        if versions["current_version"]:
            print("-" * 50)
            print(versions["current_version"])
        else:
            print("未找到当前版本的函数代码")
            
        print("\n" + "=" * 60)
        print(f"上一个提交: {versions['previous_commit']}")
        if versions["previous_version"]:
            print("-" * 50)
            print(versions["previous_version"])
        else:
            print("未找到上一版本的函数代码")
            
        # 保存结果
        if versions["current_version"] or versions["previous_version"]:
            output_dir = "./downloaded_functions"
            os.makedirs(output_dir, exist_ok=True)
            result_file = os.path.join(output_dir, f"{function_name}_versions.json")
            
            with open(result_file, "w", encoding="utf-8") as f:
                json.dump(versions, f, ensure_ascii=False, indent=2)
                
            print(f"\n结果已保存到: {result_file}")
            
    else:
        print("无效选择")

if __name__ == "__main__":
    main() 
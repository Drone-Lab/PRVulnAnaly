import json
import os
import re
import time
import datetime

def extract_modified_functions(patch_text):
    """
    从补丁文本中提取被修改的函数名
    
    Args:
        patch_text: 补丁文本
        
    Returns:
        被修改的函数名集合
    """
    function_names = set()
    
    # 1. 提取补丁头部的函数名 (修复识别Land::on_activation这样没有返回类型的函数)
    # 处理形如 @@ -58,8 +58,9 @@ Land::on_activation() 或 @@ -322,9 +322,8 @@ void RTL::on_active()
    header_pattern = r'@@ -\d+,\d+ \+\d+,\d+ @@(?:\s+(?:[\w\s:*&<>]+))?\s+(\w+)::(\w+)\s*\('
    header_matches = re.findall(header_pattern, patch_text)
    for match in header_matches:
        class_name, func_name = match
        full_name = f"{class_name}::{func_name}"
        function_names.add(full_name)
    
    # 2. 处理补丁内容中修改/删除的函数
    lines = patch_text.split('\n')
    for line in lines:
        # 只处理删除行（以-开头）
        if line.startswith('-'):
            content_line = line[1:].strip()
            if not content_line:
                continue
            
            # 查找删除的类成员函数定义，如: void RTL::on_active()
            func_def_match = re.search(r'([\w\s:*&<>]+)?\s+(\w+)::(\w+)\s*\(', content_line)
            if func_def_match:
                class_name = func_def_match.group(2)
                func_name = func_def_match.group(3)
                full_name = f"{class_name}::{func_name}"
                function_names.add(full_name)
            
            # 查找删除的独立函数定义，如: void calculate_position()
            standalone_func_match = re.search(r'^\s*([\w\s:*&<>]+)\s+(\w+)\s*\([^)]*\)', content_line)
            if standalone_func_match and '::' not in content_line:
                func_name = standalone_func_match.group(2)
                if func_name not in ['if', 'while', 'for', 'switch']:  # 排除关键字
                    function_names.add(func_name)
    
    # 3. 特别处理可能的函数重命名情况（删除旧函数名，添加新函数名）
    # 查找成对的删除/添加行，提取删除的函数名
    rename_pattern = []
    for i in range(len(lines) - 1):
        if lines[i].startswith('-') and lines[i+1].startswith('+'):
            old_line = lines[i][1:].strip()
            new_line = lines[i+1][1:].strip()
            
            # 检查是否是相似的函数定义行（可能是重命名）
            old_func_match = re.search(r'([\w\s:*&<>]+)?\s+(\w+)::(\w+)\s*\(', old_line)
            new_func_match = re.search(r'([\w\s:*&<>]+)?\s+(\w+)::(\w+)\s*\(', new_line)
            
            if old_func_match and new_func_match:
                old_class = old_func_match.group(2)
                old_func = old_func_match.group(3)
                new_class = new_func_match.group(2)
                new_func = new_func_match.group(3)
                
                # 如果类名相同但函数名不同，认为是重命名
                if old_class == new_class and old_func != new_func:
                    old_full_name = f"{old_class}::{old_func}"
                    function_names.add(old_full_name)
    
    return function_names

def analyze_json_patches(json_file="px4_navigator_prs.json"):
    """
    分析JSON文件中的补丁，提取被修改的函数名并更新JSON
    
    Args:
        json_file: JSON文件路径
        
    Returns:
        处理的PR数量
    """
    try:
        # 加载JSON文件
        with open(json_file, 'r', encoding='utf-8') as f:
            pr_data = json.load(f)
        
        print(f"成功加载 {len(pr_data)} 个PR数据")
        
        # 创建备份
        backup_file = f"{json_file}.bak"
        with open(backup_file, 'w', encoding='utf-8') as f:
            json.dump(pr_data, f, ensure_ascii=False, indent=2)
        print(f"已创建备份文件: {backup_file}")
        
        # 记录统计信息
        total = len(pr_data)
        processed = 0
        skipped = 0
        failed = 0
        
        # 处理每个PR
        for i, pr in enumerate(pr_data):
            pr_number = pr.get('number')
            if not pr_number:
                print(f"跳过第 {i+1} 项: 未找到PR编号")
                skipped += 1
                continue
            
            print(f"[{i+1}/{total}] 处理PR #{pr_number}: {pr.get('title', '')}")
            
            # 检查是否有patches字段
            if 'patches' not in pr or not pr['patches']:
                print(f"  PR #{pr_number} 无补丁信息")
                skipped += 1
                continue
            
            try:
                # 分析每个文件的补丁
                patches = pr['patches']
                all_modified_functions = set()
                file_modified_functions = {}
                
                for filename, patch_info in patches.items():
                    if 'patch' not in patch_info or not patch_info['patch']:
                        print(f"  文件 {filename} 无补丁内容")
                        continue
                    
                    patch_text = patch_info['patch']
                    functions = extract_modified_functions(patch_text)
                    
                    if functions:
                        file_modified_functions[filename] = list(functions)
                        all_modified_functions.update(functions)
                        print(f"  文件 {filename} 找到 {len(functions)} 个被修改的函数:")
                        for func in sorted(functions):
                            print(f"    - {func}")
                
                # 更新PR对象
                if all_modified_functions:
                    pr['modified_functions'] = {
                        'all': list(all_modified_functions),
                        'by_file': file_modified_functions
                    }
                    processed += 1
                else:
                    pr['modified_functions'] = {
                        'all': [],
                        'by_file': {}
                    }
                    print(f"  未找到任何被修改的函数")
                
            except Exception as e:
                failed += 1
                print(f"处理PR #{pr_number} 时出错: {str(e)}")
                import traceback
                traceback.print_exc()
        
        # 保存结果
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(pr_data, f, ensure_ascii=False, indent=2)
        
        # 打印统计信息
        print("\n分析完成！")
        print(f"总计: {total} 个PR")
        print(f"成功提取函数: {processed} 个")
        print(f"跳过: {skipped} 个")
        print(f"失败: {failed} 个")
        
        return processed
        
    except Exception as e:
        print(f"处理JSON文件时出错: {str(e)}")
        import traceback
        traceback.print_exc()
        return 0

def main():
    # 分析JSON文件
    processed = analyze_json_patches()

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import datetime

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
        print(f"成功加载JSON文件: {json_file}，共有 {len(data)} 条记录")
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

def find_missing_functions():
    """
    查找在px4_navigator_prs.json中但不在previous_functions.json中的函数
    
    Returns:
        missing_functions_data: 缺失函数的统计信息
    """
    # 文件路径
    pr_file = "px4_navigator_prs.json"
    func_file = "previous_functions.json"
    output_file = "missing_functions.json"
    
    # 加载JSON数据
    prs_data = load_json_file(pr_file)
    functions_data = load_json_file(func_file)
    
    # 检查数据有效性
    if not prs_data or not functions_data:
        print("无法获取必要的数据，请确保两个JSON文件都存在且格式正确")
        return None
    
    # 统计数据
    total_functions = 0  # 所有PR中涉及的函数总数
    missing_functions = 0  # 未找到定义的函数数量
    pr_with_missing = 0  # 有缺失函数的PR数量
    missing_data = {}  # 保存缺失函数的详细信息
    
    # 遍历所有PR
    for pr in prs_data:
        pr_number = str(pr.get('number'))
        pr_missing_functions = []
        
        # 检查是否有modified_functions字段
        if 'modified_functions' not in pr:
            continue
        
        modified_functions = pr.get('modified_functions', {})
        all_functions = modified_functions.get('all', [])
        total_functions += len(all_functions)
        
        if not all_functions:
            continue
        
        # 检查哪些函数不在previous_functions.json中
        for function_name in all_functions:
            # 检查函数是否已经被处理
            if pr_number in functions_data:
                if function_name in functions_data[pr_number]:
                    continue  # 函数已存在于previous_functions.json中
            
            # 如果不存在，则记录此函数
            pr_missing_functions.append(function_name)
            missing_functions += 1
        
        # 记录此PR的缺失函数
        if pr_missing_functions:
            pr_with_missing += 1
            missing_data[pr_number] = {
                "title": pr.get('title', ''),
                "missing_functions": pr_missing_functions,
                "count": len(pr_missing_functions)
            }
    
    # 生成统计结果
    stats = {
        "timestamp": datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "summary": {
            "total_prs": len(prs_data),
            "total_functions": total_functions,
            "missing_functions": missing_functions,
            "missing_percentage": round(missing_functions / total_functions * 100, 2) if total_functions > 0 else 0,
            "prs_with_missing": pr_with_missing,
            "prs_missing_percentage": round(pr_with_missing / len(prs_data) * 100, 2) if len(prs_data) > 0 else 0
        },
        "details": missing_data
    }
    
    # 保存结果到文件
    save_json_file(stats, output_file)
    
    return stats

def main():
    print("开始统计缺失函数...")
    stats = find_missing_functions()
    
    if stats:
        summary = stats["summary"]
        print("\n--- 统计结果摘要 ---")
        print(f"总PR数量: {summary['total_prs']}")
        print(f"总函数数量: {summary['total_functions']}")
        print(f"缺失函数数量: {summary['missing_functions']} ({summary['missing_percentage']}%)")
        print(f"有缺失函数的PR数量: {summary['prs_with_missing']} ({summary['prs_missing_percentage']}%)")
        print("详细信息已保存到 missing_functions.json")

if __name__ == "__main__":
    main() 
import json
import os

def load_json_file(file_path):
    """
    加载JSON文件
    
    Args:
        file_path: JSON文件路径
        
    Returns:
        加载的JSON数据，如果失败则返回None
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        print(f"成功加载JSON文件: {file_path}")
        print(f"文件包含 {len(data)} 个对象")
        return data
    except Exception as e:
        print(f"加载JSON文件失败: {str(e)}")
        return None

def find_pr_logic_errors(data, pr_numbers):
    """
    在JSON数据中查找指定PR号的isLogicError字段值
    
    Args:
        data: JSON数据列表
        pr_numbers: 要查找的PR号列表
        
    Returns:
        PR号到isLogicError值的映射字典
    """
    if not isinstance(data, list):
        print("错误: JSON数据不是列表格式")
        return {}
    
    results = {}
    found_count = 0
    
    # 将PR号转换为整数，方便匹配
    pr_numbers_set = set(map(int, pr_numbers))
    
    # 查找每个PR
    for item in data:
        if not isinstance(item, dict):
            continue
            
        pr_number = item.get('number')
        if pr_number and pr_number in pr_numbers_set:
            # 提取isLogicError字段值
            is_logic_error = item.get('isLogicError')
            logic_error_desc = item.get('logicErrorDescription', '')
            
            # 截断描述，只显示一部分
            if logic_error_desc and len(logic_error_desc) > 50:
                logic_error_desc = logic_error_desc[:50] + "..."
                
            results[pr_number] = {
                'isLogicError': is_logic_error,
                'description': logic_error_desc
            }
            found_count += 1
            
            # 如果已找到所有PR，则提前结束
            if found_count == len(pr_numbers_set):
                break
    
    return results

def main():
    # 配置
    file_path = "px4_navigator_prs.json"
    
    # 要查找的PR号列表
    pr_numbers = [
        23845,
        24115,
        22532,
        22984,
        23501,
        22773,
        21775,
        21782,
        21602,
        21714
    ]
    
    # 检查文件是否存在
    if not os.path.exists(file_path):
        print(f"错误: 文件不存在 {file_path}")
        return
    
    # 加载JSON文件
    data = load_json_file(file_path)
    if not data:
        return
    
    # 查找指定PR的isLogicError值
    print(f"正在查找 {len(pr_numbers)} 个PR的isLogicError值...")
    results = find_pr_logic_errors(data, pr_numbers)
    
    # 打印结果
    print("\n查找结果:")
    print("-" * 80)
    print(f"{'PR号':<10} {'isLogicError':<15} {'描述'}")
    print("-" * 80)
    
    for pr_number in pr_numbers:
        pr_result = results.get(pr_number)
        if pr_result:
            is_logic_error = pr_result['isLogicError']
            description = pr_result['description']
            print(f"{pr_number:<10} {str(is_logic_error):<15} {description}")
        else:
            print(f"{pr_number:<10} {'未找到':<15} {'未找到此PR或字段不存在'}")
    
    # 统计信息
    found_count = len(results)
    print("-" * 80)
    print(f"总计: 查找了 {len(pr_numbers)} 个PR，找到 {found_count} 个，未找到 {len(pr_numbers) - found_count} 个")
    
    # 统计isLogicError为true和false的数量
    true_count = sum(1 for result in results.values() if result['isLogicError'] is True)
    false_count = sum(1 for result in results.values() if result['isLogicError'] is False)
    none_count = sum(1 for result in results.values() if result['isLogicError'] is None)
    
    print(f"isLogicError值统计: True: {true_count}, False: {false_count}, None: {none_count}")

if __name__ == "__main__":
    main()

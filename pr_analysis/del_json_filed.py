import json
import os
import time
import datetime

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

def save_json_file(data, file_path):
    """
    保存JSON数据到文件
    
    Args:
        data: 要保存的JSON数据
        file_path: 目标文件路径
        
    Returns:
        是否保存成功
    """
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"成功保存JSON文件: {file_path}")
        return True
    except Exception as e:
        print(f"保存JSON文件失败: {str(e)}")
        return False

def delete_fields_from_json(data, fields_to_delete):
    """
    从JSON数据中删除指定字段
    
    Args:
        data: JSON数据
        fields_to_delete: 要删除的字段列表
        
    Returns:
        (修改后的JSON数据, 修改的对象数量)
    """
    if not isinstance(data, list):
        print("错误: JSON数据不是列表格式")
        return data, 0
    
    modified_count = 0
    fields_found = {field: 0 for field in fields_to_delete}
    
    for item in data:
        if not isinstance(item, dict):
            continue
            
        item_modified = False
        for field in fields_to_delete:
            if field in item:
                del item[field]
                fields_found[field] += 1
                item_modified = True
                
        if item_modified:
            modified_count += 1
    
    # 打印删除的字段统计信息
    for field, count in fields_found.items():
        print(f"删除字段 '{field}': {count} 个")
    
    return data, modified_count

def main():
    
    # 配置
    file_path = "px4_navigator_prs.json"
    fields_to_delete = ["created_at"]
    backup_file = f"{file_path}.bak"
    
    # 检查文件是否存在
    if not os.path.exists(file_path):
        print(f"错误: 文件不存在 {file_path}")
        return
    
    # 创建备份
    try:
        with open(file_path, 'r', encoding='utf-8') as source:
            with open(backup_file, 'w', encoding='utf-8') as target:
                target.write(source.read())
        print(f"已创建备份文件: {backup_file}")
    except Exception as e:
        print(f"创建备份文件失败: {str(e)}")
        return
    
    # 加载JSON文件
    data = load_json_file(file_path)
    if not data:
        return
    
    # 删除字段
    print(f"正在删除字段: {', '.join(fields_to_delete)}")
    modified_data, modified_count = delete_fields_from_json(data, fields_to_delete)
    
    if modified_count > 0:
        # 保存修改后的文件
        if save_json_file(modified_data, file_path):
            print(f"已成功修改 {modified_count} 个对象，删除了指定字段")
        else:
            print("保存修改后的文件失败")
    else:
        print("未找到需要删除的字段，文件未修改")


if __name__ == "__main__":
    main()

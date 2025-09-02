import json

def analyze_prs_json(filename):
    try:
        # 读取 JSON 文件
        with open(filename, 'r', encoding='utf-8') as file:
            data = json.load(file)

        # 确保数据是一个列表
        if not isinstance(data, list):
            print("JSON 文件内容不是一个数组。")
            return

        total_objects = len(data)
        merged_true_count = 0
        logic_error_count = 0

        # 遍历每个对象，统计 merged 为 true 的数量
        for item in data:
            if isinstance(item, dict) and item.get("merged") is True:
                merged_true_count += 1
                # 统计已合并且isLogicError为true的数量
                if item.get("isLogicError") is True:
                    logic_error_count += 1

        # 输出结果
        print(f"总对象数量: {total_objects}")
        print(f"merged 为 true 的对象数量: {merged_true_count}")
        print(f"merged 为 true 且 isLogicError 为 true 的对象数量: {logic_error_count}")
        
        # 计算比例
        if merged_true_count > 0:
            ratio = logic_error_count / merged_true_count * 100
            print(f"已合并PR中逻辑错误的比例: {ratio:.2f}%")

    except FileNotFoundError:
        print(f"文件 {filename} 未找到，请检查文件路径。")
    except json.JSONDecodeError as e:
        print(f"JSON 解析错误: {e}")
    except Exception as e:
        print(f"发生错误: {e}")

# 使用示例
if __name__ == "__main__":
    analyze_prs_json("px4_navigator_prs.json")
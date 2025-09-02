import re
import statistics

def extract_iteration_times(file_path):
    """
    从文件中提取迭代时间
    
    Args:
        file_path: 文件路径
        
    Returns:
        提取到的迭代时间列表（秒）
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 使用正则表达式提取格式为 "X.XXs/it" 的迭代时间
        pattern = r'(\d+\.\d+)s/it'
        matches = re.findall(pattern, content)
        
        # 转换为浮点数
        iteration_times = [float(t) for t in matches]
        
        return iteration_times
    
    except Exception as e:
        print(f"提取迭代时间时出错: {str(e)}")
        return []

def analyze_iteration_times(times):
    """
    分析迭代时间，计算统计信息
    
    Args:
        times: 迭代时间列表
        
    Returns:
        包含统计信息的字典
    """
    if not times:
        return {
            "count": 0,
            "average": None,
            "min": None,
            "max": None,
            "median": None
        }
    
    return {
        "count": len(times),
        "average": sum(times) / len(times),
        "min": min(times),
        "max": max(times),
        "median": statistics.median(times)
    }

def main():
    # 文件路径
    file_path = "avg_time.txt"
    
    # 提取迭代时间
    iteration_times = extract_iteration_times(file_path)
    
    if not iteration_times:
        print("未找到有效的迭代时间数据")
        return
    
    # 分析数据
    stats = analyze_iteration_times(iteration_times)
    
    # 打印结果
    print("\n迭代时间统计:")
    print("-" * 40)
    print(f"总样本数: {stats['count']} 个")
    print(f"平均迭代时间: {stats['average']:.2f} 秒")
    print(f"最小迭代时间: {stats['min']:.2f} 秒")
    print(f"最大迭代时间: {stats['max']:.2f} 秒")
    print(f"中位数迭代时间: {stats['median']:.2f} 秒")
    
    # 展示所有提取到的迭代时间
    print("\n所有迭代时间 (秒):")
    for i, t in enumerate(iteration_times):
        print(f"{i+1}: {t:.2f}", end="  ")
        if (i + 1) % 5 == 0:  # 每5个换一行
            print()
    
    print("\n")
    print(f"总计: {len(iteration_times)} 个样本，平均迭代时间: {stats['average']:.2f} 秒")

if __name__ == "__main__":
    main()

import json
import os
import requests
import time
import datetime

def get_navigator_patches(pr_number, headers, session=None):
    """
    获取PR中修改的src/modules/navigator文件夹下的文件补丁
    
    Args:
        pr_number: PR编号
        headers: GitHub API的请求头
        session: 请求会话（可选）
        
    Returns:
        包含补丁信息的字典，键为文件名，值为补丁信息
    """
    api_url = f"https://api.github.com/repos/PX4/PX4-Autopilot/pulls/{pr_number}/files"
    
    if session is None:
        session = requests.Session()
    
    # 添加重试机制
    for attempt in range(3):
        try:
            response = session.get(api_url, headers=headers, timeout=10)
            if response.status_code == 200:
                break
            elif response.status_code == 403:
                rate_limit = response.headers.get('X-RateLimit-Remaining', 'unknown')
                reset_time = response.headers.get('X-RateLimit-Reset', 0)
                if reset_time:
                    reset_time = datetime.datetime.fromtimestamp(int(reset_time))
                    print(f"API速率限制: 剩余请求数 {rate_limit}, 重置时间 {reset_time}")
                print(f"API速率限制，等待60秒...")
                time.sleep(60)
                continue
            else:
                print(f"获取PR文件失败，状态码: {response.status_code}")
                print(f"错误信息: {response.text}")
                return {}
        except Exception as e:
            print(f"请求失败，尝试重试 ({attempt + 1}/3): {str(e)}")
            time.sleep(5)
            continue
    else:
        print(f"获取PR #{pr_number} 文件失败，已达到最大重试次数")
        return {}
    
    try:
        files = response.json()
        navigator_files = {}
        
        # 筛选出navigator文件夹下的文件
        for file in files:
            filename = file.get("filename", "")
            if filename.startswith("src/modules/navigator/"):
                navigator_files[filename] = {
                    "filename": filename,
                    "status": file.get("status"),
                    "additions": file.get("additions"),
                    "deletions": file.get("deletions"),
                    "changes": file.get("changes"),
                    "patch": file.get("patch"),
                    "blob_url": file.get("blob_url")
                }
        
        return navigator_files
    except Exception as e:
        print(f"解析PR #{pr_number} 的文件时出错: {str(e)}")
        return {}

def update_json_with_patches(json_file="px4_navigator_prs.json"):
    """
    更新JSON文件中的PR信息，添加补丁信息
    
    Args:
        json_file: JSON文件路径
        
    Returns:
        更新的PR数量
    """
    # 从环境变量获取GitHub token
    github_token = os.getenv("GITHUB_AUTHORIZATION")
    
    # 设置请求头
    headers = {
        "Authorization": f"{github_token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Github-PR-Patch-Extractor"
    }
    
    # 创建会话以重用连接
    session = requests.Session()
    
    try:
        # 加载原始JSON数据
        with open(json_file, 'r', encoding='utf-8') as f:
            pr_data = json.load(f)
        
        print(f"成功加载 {len(pr_data)} 个PR数据")
        
        # 创建备份
        backup_file = f"{json_file}.bak"
        with open(backup_file, 'w', encoding='utf-8') as f:
            json.dump(pr_data, f, ensure_ascii=False, indent=2)
        print(f"已创建备份文件: {backup_file}")
        
        # 统计信息
        total = len(pr_data)
        updated = 0
        skipped = 0
        failed = 0
        
        # 记录开始时间
        start_time = time.time()
        
        # 处理每个PR
        for i, pr in enumerate(pr_data):
            pr_number = pr.get('number')
            if not pr_number:
                print(f"跳过第 {i+1} 项: 未找到PR编号")
                skipped += 1
                continue
            
            # 如果已有patches字段，则跳过
            if 'patches' in pr:
                print(f"跳过PR #{pr_number}: 已有补丁信息")
                skipped += 1
                continue
            
            try:
                print(f"\n[{i+1}/{total}] 处理PR #{pr_number}: {pr.get('title', '')}")
                
                # 获取补丁信息
                patches = get_navigator_patches(pr_number, headers, session)
                
                if patches:
                    # 更新PR数据
                    pr['patches'] = patches
                    updated += 1
                    
                    # 打印找到的文件
                    print(f"已找到 {len(patches)} 个navigator文件的补丁:")
                    for filename in patches.keys():
                        print(f"  - {filename}")
                    
                    # 每处理10个PR保存一次，避免数据丢失
                    if updated % 10 == 0:
                        with open(json_file, 'w', encoding='utf-8') as f:
                            json.dump(pr_data, f, ensure_ascii=False, indent=2)
                        print(f"已保存中间结果，已处理 {updated} 个PR")
                else:
                    print(f"PR #{pr_number} 中未找到navigator文件的修改")
                    # 添加空的patches字段
                    pr['patches'] = {}
                
                # 避免触发GitHub API限制
                time.sleep(0.5)
                
            except Exception as e:
                failed += 1
                print(f"处理PR #{pr_number} 时出错: {str(e)}")
                continue
        
        # 保存最终结果
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(pr_data, f, ensure_ascii=False, indent=2)
        
        # 计算总耗时
        elapsed_time = time.time() - start_time
        hours, remainder = divmod(elapsed_time, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        # 打印统计信息
        print(f"\n处理完成！")
        print(f"总计: {total} 个PR")
        print(f"更新: {updated} 个")
        print(f"跳过: {skipped} 个")
        print(f"失败: {failed} 个")
        print(f"总耗时: {int(hours)}小时 {int(minutes)}分钟 {seconds:.2f}秒")
        
        return updated
        
    except Exception as e:
        print(f"处理JSON文件时出错: {str(e)}")
        return 0

def main():
    # 更新JSON文件
    json_file = "px4_navigator_prs.json"
    print(f"开始处理文件: {json_file}")
    
    updated = update_json_with_patches(json_file)

    print(f"成功更新 {updated} 个PR的补丁信息")

if __name__ == "__main__":
    main() 
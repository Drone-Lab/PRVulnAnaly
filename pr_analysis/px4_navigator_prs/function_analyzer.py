import json
import os
from typing import List, Dict, Set, Tuple
from langchain.schema import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pathlib import Path

def load_functions(json_file: str, limit: int = 1000) -> List[Dict]:
    """
    加载函数数据，限制处理数量
    """
    with open(json_file, 'r', encoding='utf-8') as f:
        functions = json.load(f)
    return functions[:limit]

def analyze_function(llm: ChatOpenAI, function_data: Dict) -> Dict:
    """
    使用LLM分析单个函数并生成描述
    """
    system_message = SystemMessage(content="""
    You are an expert code analysis assistant. Your task is to analyze Python functions and generate **implementation-focused documentation** that precisely describes how the function works.
    
    **Output Requirements:**
    1. Strictly use this JSON format:
    {
        "detailed_description": "Comprehensive explanation of function implementation",
        "implementation_details": [
            "Step-by-step technical breakdown of key operations",
            "Description of algorithms and data transformations",
            "Edge cases and error handling approaches"
        ],
        "parameters": [
            {
                "name": "param_name",
                "type": "precise_type",
                "usage": "How parameter is used in implementation",
                "constraints": "Any limits/requirements"
            }
        ],
        "return_behavior": {
            "type": "return_type",
            "description": "Detailed conditions for return values",
            "side_effects": "Any state changes or external interactions"
        }
    }
    
    **Key Guidelines:**
    - `detailed_description`: 60-80 word technical summary of core implementation
    - `implementation_details`: 3-5 bullet points exposing internal logic
    - Types: Use precise Python types (e.g., `dict[str, pd.DataFrame]`)
    - Focus on implementation specifics:
      • Describe actual code behavior, not just purpose
      • Explain algorithms, data flows, and transformations
      • Note edge case handling and error conditions
      • Mention time/space complexity if apparent
    - Parameters: Explain how each is used internally
    - Return behavior: Specify conditions for different return values
    - Include all implementation-relevant exceptions
    """)

    # Constructed prompt
    prompt = f"""
    Conduct a deep implementation analysis of this Python function:
    
    ## Function Context
    - Name: `{function_data['name']}`
    - Class: `{function_data['class'] or 'Global function'}`
    - Enclosing Function: `{function_data['parent_function'] or 'None'}`
    - Docstring: {function_data['doc_string'] or 'No documentation available'}
    
    ## Implementation Source Code
    ```python
    {function_data['body']}
    """

    messages = [
        system_message,
        HumanMessage(content=prompt)
    ]

    try:
        response = llm.invoke(messages)
        return json.loads(response.content)
    except Exception as e:
        print(f"分析函数 {function_data['name']} 时出错: {str(e)}")
        return None

def get_function_identifier(func: Dict) -> str:
    """
    生成函数的唯一标识符
    """
    return f"{func['class']}::{func['name']}" if func['class'] else func['name']

def find_new_functions(source_json: str, target_json: str) -> Tuple[List[Dict], Dict]:
    """
    比较两个JSON文件，找出需要新增分析的函数
    
    Args:
        source_json: 源AST解析文件路径
        target_json: 目标LLM分析文件路径
    
    Returns:
        Tuple[List[Dict], Dict]: (需要新增分析的函数列表, 已存在的分析结果)
    """
    # 加载源文件（AST解析结果）
    with open(source_json, 'r', encoding='utf-8') as f:
        source_functions = json.load(f)
    
    # 加载目标文件（如果存在）
    existing_docs = {}
    try:
        with open(target_json, 'r', encoding='utf-8') as f:
            target_functions = json.load(f)
            # 构建已存在函数的映射
            for func in target_functions:
                if 'llm_documentation' in func:
                    existing_docs[get_function_identifier(func)] = func
    except FileNotFoundError:
        print(f"目标文件 {target_json} 不存在，将创建新文件")
        target_functions = []
    
    # 找出需要新增分析的函数
    new_functions = []
    for func in source_functions:
        func_id = get_function_identifier(func)
        if func_id not in existing_docs:
            new_functions.append(func)
    
    return new_functions, existing_docs

def incremental_update_functions(source_json: str, target_json: str):
    """
    增量更新函数文档
    """
    # 初始化LLM
    llm = ChatOpenAI(
        model="o4-mini",
        api_key=os.getenv('OPENAI_API_KEY')
    )
    
    # 找出需要新增分析的函数
    new_functions, existing_docs = find_new_functions(source_json, target_json)
    print(f"发现 {len(new_functions)} 个新函数需要分析")
    
    # 分析新函数
    updated_functions = []
    for i, func in enumerate(new_functions):
        func_id = get_function_identifier(func)
        print(f"\n处理新函数 {i+1}/{len(new_functions)}: {func_id}")
        doc = analyze_function(llm, func)
        if doc:
            func['llm_documentation'] = doc
            updated_functions.append(func)
            print(f"成功生成文档：{doc['detailed_description'][:100]}...")
    
    # 合并新旧结果
    final_functions = list(existing_docs.values()) + updated_functions
    
    # 保存更新后的数据
    with open(target_json, 'w', encoding='utf-8') as f:
        json.dump(final_functions, f, indent=4, ensure_ascii=False)
    print(f"\n已更新文件：{target_json}")
    print(f"总计处理：{len(updated_functions)} 个新函数")
    print(f"文件中总函数数量：{len(final_functions)}")

def main():
    source_json = "../source_code/vehicle_test_suite_ASTparse.json"
    target_json = "../source_code/vehicle_test_suite_AST_LLM_parse.json"
    incremental_update_functions(source_json, target_json)

if __name__ == "__main__":
    main() 
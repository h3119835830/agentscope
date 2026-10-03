"""Known event coverage limits, separate from compiler acceptance."""
import re

def runtime_limits_for(dsl):
    if not dsl or not re.search(r"\b(?:write|unlink)\s+file\b",dsl):
        return []
    return [{"code":"file_creation_directory_entry",
        "detail":"写入被拒绝时，新建文件可能已留下空目录项。文件内容写入与删除限制不代表所有文件系统元数据变更都已被阻止；完整目录不变性未验收。"}]

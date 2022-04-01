import re


def mask_sensitive(inp: str) -> str:
    ret = inp
    ret = re.sub(r"(?<=[\"']password[\"']:\s[\"'])[^\"']*", "***", ret)
    ret = re.sub(r"(?<=[\"']key[\"']:\s[\"'])[^\"']*", "***", ret)
    ret = re.sub(r"(?<=key=b[\"'])[^\"']*", "***", ret)
    ret = re.sub(r"(?<=key=[\"'])[^\"']*", "***", ret)
    ret = re.sub(r"(?<=password=[\"'])[^\"']*", "***", ret)
    ret = re.sub(r"(?<=['\"]data['\"]:).*", "***", ret)
    ret = re.sub(r"(?<=[\"']params[\"']:).*", "***", ret)
    ret = re.sub(r"(?<=params <).*", "***", ret)
    return ret

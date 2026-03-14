from typing import Any, Dict
from datetime import datetime

def deterministic_validator(
    slm_output: Dict[str, Any],
    pattern_output: Dict[str, Any]
) -> Dict[str, Any]:
    critical_fields = ["total_amount_due", "payment_due_date", "minimum_amount_due", "credit_limit"]
    result = {}

    for field in set(slm_output) | set(pattern_output):
        s = slm_output.get(field)
        p = pattern_output.get(field)
        

        if field in critical_fields:
            print(f"Comparing field '{field}': SLM={s}, Pattern={p}")
            if p is None and s is not None:
                result[field] = s
            elif s is None and p is not None:
                result[field] = p
            elif p == s:
                result[field] = p
            else:
                print(f"Conflict in field '{field}': SLM='{s}' vs Pattern='{p}'. Choosing SLM value.")
                if field in ["payment_due_date", "credit_limit"]:
                
                    orig_s = s
                    orig_p = p
    
                    s = datetime.strptime(s, "%Y-%m-%d") if isinstance(s, str) else s
                    p = datetime.strptime(p, "%Y-%m-%d") if isinstance(p, str) else p
                    print(type(s), type(p))
                    if p > s:
                        result[field] = orig_p
                    elif s > p:
                        result[field] = orig_s
                    else:
                        result[field] = orig_s
                else:
                    result[field] = s

        else:
            result[field] = p if p is not None else s

    return result
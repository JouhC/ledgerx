from typing import Any, Dict, List
from datetime import datetime, timedelta

def deterministic_validator(
    slm_output: Dict[str, Any],
    pattern_output: Dict[str, Any],
    required_fields: List[str]
) -> Dict[str, Any]:
    critical_fields = ["total_amount_due", "payment_due_date", "minimum_amount_due", "credit_limit"]
    result = {}

    for field in required_fields:
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
                    print(type(s), type(p))

                    orig_s = s
                    orig_p = p
    
                    s = datetime.strptime(s, "%Y-%m-%d") if isinstance(s, str) else s
                    p = datetime.strptime(p, "%Y-%m-%d") if isinstance(p, str) else p
                    
                    if p > s:
                        if field == "payment_due_date":
                            statement_date = datetime.strptime(result["statement_date"], "%Y-%m-%d") if isinstance(result["statement_date"], str) else result["statement_date"]
                            if p - statement_date > timedelta(30):
                                result[field] = orig_s
                                continue

                        result[field] = orig_p
                    elif s > p:
                        if field == "payment_due_date":
                            statement_date = datetime.strptime(result["statement_date"], "%Y-%m-%d") if isinstance(result["statement_date"], str) else result["statement_date"]
                            if s - statement_date > timedelta(30):
                                result[field] = orig_p
                                continue

                        result[field] = orig_s
                    else:
                        result[field] = orig_s
                else:
                    result[field] = s

        else:
            result[field] = p if p is not None else s

    return result
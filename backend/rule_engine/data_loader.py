# rule_engine/data_loader.py

import json
import os
from typing import Dict, Optional

class RuleDataLoader:
    """JSON 규칙 데이터 로더"""
    
    def __init__(self, rules_dir: str = 'data/rules'):
        self.rules_dir = rules_dir
        self._cache = {}
    
    def load_json(self, filename: str) -> Dict:
        """JSON 파일 로드 (캐싱)"""
        
        if filename in self._cache:
            return self._cache[filename]
        
        filepath = os.path.join(self.rules_dir, filename)
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self._cache[filename] = data
                return data
        except FileNotFoundError:
            raise FileNotFoundError(f"규칙 파일을 찾을 수 없습니다: {filepath}")
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON 파일 파싱 오류: {filepath} - {e}")
    
    def get_regulation_areas(self) -> Dict:
        """규제지역 데이터"""
        return self.load_json('regulation_areas.json')
    
    def get_ltv_rules(self) -> Dict:
        """LTV 규제 데이터"""
        return self.load_json('ltv_rules.json')
    
    def get_dti_dsr_rules(self) -> Dict:
        """DTI/DSR 규제 데이터"""
        return self.load_json('dti_dsr_rules.json')
    
    def get_policy_loans(self) -> Dict:
        """정책대출 데이터"""
        return self.load_json('policy_loans.json')

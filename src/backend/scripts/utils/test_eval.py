import sys
import os
sys.path.insert(0, os.path.join(os.path.abspath(os.path.dirname(__file__)), 'src'))

from backend.ner_pipeline.zero_shot.evaluate_zero_shot import evaluate_zero_shot

if __name__ == '__main__':
    evaluate_zero_shot(limit=5)

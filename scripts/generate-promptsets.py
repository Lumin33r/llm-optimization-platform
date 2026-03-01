#!/usr/bin/env python3
"""Generate all promptsets for the LLM Optimization Platform.

Usage:
    python scripts/generate-promptsets.py [--output-dir data/promptsets]

Produces:
    data/promptsets/canary/promptset.jsonl     (50 prompts - deployment health)
    data/promptsets/canary/manifest.json
    data/promptsets/performance/promptset.jsonl (100 prompts - throughput/latency)
    data/promptsets/performance/manifest.json
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'services', 'data-engine'))

import argparse
from pathlib import Path
from generator import PromptsetGenerator


# --------------- Canary Prompts (Deployment Health) ---------------
CANARY_PROMPTS = [
    # Math / simple reasoning
    {"prompt_id": "canary-001", "prompt": "What is 2 + 2?", "expected_contains": ["4"], "scenario_id": "math_simple", "max_tokens": 50},
    {"prompt_id": "canary-002", "prompt": "What is 10 times 5?", "expected_contains": ["50"], "scenario_id": "math_simple", "max_tokens": 50},
    {"prompt_id": "canary-003", "prompt": "What is 100 divided by 4?", "expected_contains": ["25"], "scenario_id": "math_simple", "max_tokens": 50},
    {"prompt_id": "canary-004", "prompt": "What is the square root of 144?", "expected_contains": ["12"], "scenario_id": "math_simple", "max_tokens": 50},
    {"prompt_id": "canary-005", "prompt": "If x = 3 and y = 7, what is x + y?", "expected_contains": ["10"], "scenario_id": "math_simple", "max_tokens": 50},

    # Knowledge / facts
    {"prompt_id": "canary-006", "prompt": "What is the capital of France?", "expected_contains": ["Paris"], "scenario_id": "knowledge", "max_tokens": 50},
    {"prompt_id": "canary-007", "prompt": "What planet is closest to the Sun?", "expected_contains": ["Mercury"], "scenario_id": "knowledge", "max_tokens": 50},
    {"prompt_id": "canary-008", "prompt": "Who wrote Romeo and Juliet?", "expected_contains": ["Shakespeare"], "scenario_id": "knowledge", "max_tokens": 50},
    {"prompt_id": "canary-009", "prompt": "What is the chemical symbol for water?", "expected_contains": ["H2O"], "scenario_id": "knowledge", "max_tokens": 50},
    {"prompt_id": "canary-010", "prompt": "How many continents are there?", "expected_contains": ["7", "seven"], "scenario_id": "knowledge", "max_tokens": 50},

    # Translation
    {"prompt_id": "canary-011", "prompt": "Translate 'hello' to Spanish.", "expected_contains": ["hola", "Hola"], "scenario_id": "translation", "max_tokens": 50},
    {"prompt_id": "canary-012", "prompt": "Translate 'thank you' to French.", "expected_contains": ["merci", "Merci"], "scenario_id": "translation", "max_tokens": 50},
    {"prompt_id": "canary-013", "prompt": "Translate 'goodbye' to German.", "expected_contains": ["Tschüss", "Auf Wiedersehen", "tschüss", "auf wiedersehen"], "scenario_id": "translation", "max_tokens": 50},

    # Completion
    {"prompt_id": "canary-014", "prompt": "Complete the sentence: The capital of France is", "expected_contains": ["Paris"], "scenario_id": "completion", "max_tokens": 50},
    {"prompt_id": "canary-015", "prompt": "Complete: Water freezes at", "expected_contains": ["0", "32", "zero"], "scenario_id": "completion", "max_tokens": 50},

    # Classification
    {"prompt_id": "canary-016", "prompt": "Is the following a fruit or vegetable: apple", "expected_contains": ["fruit", "Fruit"], "scenario_id": "classification", "max_tokens": 50},
    {"prompt_id": "canary-017", "prompt": "Is the number 7 odd or even?", "expected_contains": ["odd", "Odd"], "scenario_id": "classification", "max_tokens": 50},

    # Lists
    {"prompt_id": "canary-018", "prompt": "List three primary colors.", "expected_contains": ["red", "blue", "yellow"], "scenario_id": "list_generation", "max_tokens": 100},
    {"prompt_id": "canary-019", "prompt": "Name three planets in our solar system.", "expected_contains": ["Earth"], "scenario_id": "list_generation", "max_tokens": 100},
    {"prompt_id": "canary-020", "prompt": "List three programming languages.", "expected_contains": ["Python"], "scenario_id": "list_generation", "max_tokens": 100},

    # Definitions
    {"prompt_id": "canary-021", "prompt": "Define 'photosynthesis' in one sentence.", "expected_contains": ["light", "plant", "energy"], "scenario_id": "definition", "max_tokens": 100},
    {"prompt_id": "canary-022", "prompt": "What is machine learning in one sentence?", "expected_contains": ["data", "learn"], "scenario_id": "definition", "max_tokens": 100},
    {"prompt_id": "canary-023", "prompt": "What is an API?", "expected_contains": ["interface", "application"], "scenario_id": "definition", "max_tokens": 100},

    # Short answers
    {"prompt_id": "canary-024", "prompt": "What year did World War II end?", "expected_contains": ["1945"], "scenario_id": "knowledge", "max_tokens": 50},
    {"prompt_id": "canary-025", "prompt": "What is the boiling point of water in Celsius?", "expected_contains": ["100"], "scenario_id": "knowledge", "max_tokens": 50},
    {"prompt_id": "canary-026", "prompt": "How many days are in a leap year?", "expected_contains": ["366"], "scenario_id": "knowledge", "max_tokens": 50},
    {"prompt_id": "canary-027", "prompt": "What is the speed of light in km/s approximately?", "expected_contains": ["300", "299"], "scenario_id": "knowledge", "max_tokens": 50},
    {"prompt_id": "canary-028", "prompt": "Who painted the Mona Lisa?", "expected_contains": ["Vinci", "Leonardo", "Da Vinci"], "scenario_id": "knowledge", "max_tokens": 50},
    {"prompt_id": "canary-029", "prompt": "What is the largest ocean on Earth?", "expected_contains": ["Pacific"], "scenario_id": "knowledge", "max_tokens": 50},
    {"prompt_id": "canary-030", "prompt": "What gas do plants absorb from the atmosphere?", "expected_contains": ["CO2", "carbon dioxide", "Carbon dioxide"], "scenario_id": "knowledge", "max_tokens": 50},

    # Reasoning
    {"prompt_id": "canary-031", "prompt": "If a train travels 60 mph for 2 hours, how far does it go?", "expected_contains": ["120"], "scenario_id": "reasoning", "max_tokens": 100},
    {"prompt_id": "canary-032", "prompt": "If I have 3 apples and give away 1, how many do I have?", "expected_contains": ["2"], "scenario_id": "reasoning", "max_tokens": 50},
    {"prompt_id": "canary-033", "prompt": "What comes next in the pattern: 2, 4, 6, 8, ?", "expected_contains": ["10"], "scenario_id": "reasoning", "max_tokens": 50},

    # More knowledge variety
    {"prompt_id": "canary-034", "prompt": "What is the currency of Japan?", "expected_contains": ["yen", "Yen"], "scenario_id": "knowledge", "max_tokens": 50},
    {"prompt_id": "canary-035", "prompt": "What is DNA an abbreviation for?", "expected_contains": ["deoxyribonucleic"], "scenario_id": "knowledge", "max_tokens": 100},
    {"prompt_id": "canary-036", "prompt": "What is the smallest prime number?", "expected_contains": ["2"], "scenario_id": "math_simple", "max_tokens": 50},
    {"prompt_id": "canary-037", "prompt": "Name the author of 'A Brief History of Time'.", "expected_contains": ["Hawking"], "scenario_id": "knowledge", "max_tokens": 50},
    {"prompt_id": "canary-038", "prompt": "What is the SI unit of force?", "expected_contains": ["Newton", "newton"], "scenario_id": "knowledge", "max_tokens": 50},
    {"prompt_id": "canary-039", "prompt": "How many legs does a spider have?", "expected_contains": ["8", "eight"], "scenario_id": "knowledge", "max_tokens": 50},
    {"prompt_id": "canary-040", "prompt": "What is the freezing point of water in Fahrenheit?", "expected_contains": ["32"], "scenario_id": "knowledge", "max_tokens": 50},

    # More completions & simple tasks
    {"prompt_id": "canary-041", "prompt": "Spell the word 'necessary'.", "expected_contains": ["n-e-c-e-s-s-a-r-y", "necessary"], "scenario_id": "simple_task", "max_tokens": 50},
    {"prompt_id": "canary-042", "prompt": "What is the opposite of 'hot'?", "expected_contains": ["cold", "Cold"], "scenario_id": "simple_task", "max_tokens": 50},
    {"prompt_id": "canary-043", "prompt": "Convert 1 kilometer to meters.", "expected_contains": ["1000", "1,000"], "scenario_id": "conversion", "max_tokens": 50},
    {"prompt_id": "canary-044", "prompt": "What is 15% of 200?", "expected_contains": ["30"], "scenario_id": "math_simple", "max_tokens": 50},
    {"prompt_id": "canary-045", "prompt": "What color do you get mixing red and blue?", "expected_contains": ["purple", "Purple", "violet", "Violet"], "scenario_id": "knowledge", "max_tokens": 50},
    {"prompt_id": "canary-046", "prompt": "Name the largest mammal.", "expected_contains": ["whale", "Whale"], "scenario_id": "knowledge", "max_tokens": 50},
    {"prompt_id": "canary-047", "prompt": "What does CPU stand for?", "expected_contains": ["central processing unit", "Central Processing Unit", "Central processing unit"], "scenario_id": "knowledge", "max_tokens": 100},
    {"prompt_id": "canary-048", "prompt": "What is gravity measured in?", "expected_contains": ["m/s", "meter", "Newton"], "scenario_id": "knowledge", "max_tokens": 100},
    {"prompt_id": "canary-049", "prompt": "How many minutes are in an hour?", "expected_contains": ["60"], "scenario_id": "knowledge", "max_tokens": 50},
    {"prompt_id": "canary-050", "prompt": "What is the tallest mountain in the world?", "expected_contains": ["Everest"], "scenario_id": "knowledge", "max_tokens": 50},
]


# --------------- Performance Prompts (Throughput & Latency) ---------------
PERFORMANCE_PROMPTS = [
    # Short bucket (~50 output tokens) — 40 prompts
    *[{"prompt_id": f"perf-s{i:03d}", "prompt": p, "target_output_tokens": 50, "scenario_id": "throughput", "max_tokens": 60}
      for i, p in enumerate([
          "Write a one-sentence summary of photosynthesis.",
          "Explain what an API is in one sentence.",
          "Define 'recursion' briefly.",
          "What is the main function of the heart?",
          "Summarize the concept of supply and demand.",
          "What is the purpose of a compiler?",
          "Define entropy in one sentence.",
          "What is the role of mitochondria?",
          "Summarize Newton's first law of motion.",
          "What does HTTP stand for and what is it?",
          "Explain what a database index does in one sentence.",
          "What is the difference between RAM and ROM?",
          "Define 'algorithm' simply.",
          "What is cloud computing in one sentence?",
          "Summarize the greenhouse effect briefly.",
          "What is TCP/IP?",
          "Define 'latency' in computing.",
          "What does DNS stand for and do?",
          "Explain what a hash function does.",
          "What is the purpose of an operating system?",
          "Define 'bandwidth' in networking.",
          "What is the difference between HTTP and HTTPS?",
          "Explain containerization in one sentence.",
          "What is a load balancer?",
          "Define 'microservices' briefly.",
          "What is version control?",
          "Explain what CI/CD means.",
          "What is a REST API?",
          "Define 'idempotent' in computing.",
          "What is the CAP theorem?",
          "Explain eventual consistency briefly.",
          "What is a message queue?",
          "Define 'sharding' in databases.",
          "What is blue-green deployment?",
          "Explain what CORS is.",
          "What is a CDN?",
          "Define 'webhook' briefly.",
          "What is OAuth?",
          "Explain what JWT stands for and does.",
          "What is GraphQL in one sentence?",
      ], start=1)],

    # Medium bucket (~200 output tokens) — 40 prompts
    *[{"prompt_id": f"perf-m{i:03d}", "prompt": p, "target_output_tokens": 200, "scenario_id": "throughput", "max_tokens": 250}
      for i, p in enumerate([
          "Explain the concept of machine learning in a short paragraph.",
          "Describe how a neural network works.",
          "Explain the difference between supervised and unsupervised learning.",
          "Describe the transformer architecture and why it matters.",
          "Explain how gradient descent works.",
          "Describe the concept of overfitting and how to prevent it.",
          "Explain what transfer learning is and why it's useful.",
          "Describe the difference between CNN and RNN.",
          "Explain what attention mechanism is in deep learning.",
          "Describe the concept of embeddings in NLP.",
          "Explain how a recommendation system works.",
          "Describe the MapReduce programming model.",
          "Explain the ACID properties of database transactions.",
          "Describe the differences between SQL and NoSQL databases.",
          "Explain how Kubernetes orchestrates containers.",
          "Describe the principles of twelve-factor app methodology.",
          "Explain how a distributed hash table works.",
          "Describe the Raft consensus algorithm.",
          "Explain the concept of eventual consistency in distributed systems.",
          "Describe how a B-tree index works in databases.",
          "Explain the concept of backpropagation.",
          "Describe how batch normalization works.",
          "Explain what dropout regularization does.",
          "Describe the concept of model quantization.",
          "Explain how LoRA fine-tuning works.",
          "Describe the difference between inference and training.",
          "Explain what KV-cache is in transformer inference.",
          "Describe how speculative decoding works.",
          "Explain the concept of model distillation.",
          "Describe how attention heads work in multi-head attention.",
          "Explain what tokenization is and common approaches.",
          "Describe the concept of prompt engineering.",
          "Explain how retrieval-augmented generation works.",
          "Describe the concept of chain-of-thought prompting.",
          "Explain what RLHF is and why it matters for LLMs.",
          "Describe the concept of model alignment.",
          "Explain how beam search works in text generation.",
          "Describe the difference between greedy and sampling decoding.",
          "Explain what temperature means in LLM generation.",
          "Describe the concept of top-k and top-p sampling.",
      ], start=1)],

    # Long bucket (~800 output tokens) — 20 prompts
    *[{"prompt_id": f"perf-l{i:03d}", "prompt": p, "target_output_tokens": 800, "scenario_id": "stress_test", "max_tokens": 900}
      for i, p in enumerate([
          "Write a detailed explanation of how large language models work, covering architecture, training, and inference.",
          "Explain the complete lifecycle of a machine learning project from data collection to deployment.",
          "Describe the evolution of natural language processing from rule-based systems to transformer models.",
          "Write a comprehensive overview of Kubernetes architecture including all major components.",
          "Explain distributed systems concepts including CAP theorem, consensus algorithms, and partition tolerance.",
          "Describe the complete observability stack for a production system including metrics, logs, and traces.",
          "Write a detailed explanation of model quantization techniques including GPTQ, AWQ, and GGUF.",
          "Explain the complete CI/CD pipeline for machine learning models from training to production.",
          "Describe the architecture of a modern data lake including ingestion, storage, and query patterns.",
          "Write about the security considerations for deploying LLMs in production environments.",
          "Explain the complete tokenization pipeline from raw text to model input tensors.",
          "Describe the evolution of attention mechanisms from basic attention to flash attention.",
          "Write about the challenges and solutions for serving LLMs at scale in production.",
          "Explain the complete fine-tuning workflow including data preparation, training, and evaluation.",
          "Describe the architecture of a modern API gateway including routing, rate limiting, and observability.",
          "Write about the principles of chaos engineering and how to implement it in a Kubernetes environment.",
          "Explain the complete monitoring strategy for an LLM serving platform.",
          "Describe the trade-offs between different model serving frameworks like vLLM, TGI, and Triton.",
          "Write about the data engineering pipeline for training data including collection, cleaning, and versioning.",
          "Explain the architecture of OpenTelemetry and how it unifies metrics, logs, and traces.",
      ], start=1)],
]


# --------------- Quant Quality Prompts (AWQ vs FP16 comparison) ---------------
QUANT_QUALITY_PROMPTS = [
    # Math precision (quantization may lose precision)
    {"prompt_id": "qq-001", "prompt": "Calculate 7^5 step by step.", "expected_contains": ["16807"], "scenario_id": "math_precision", "max_tokens": 200, "category": "math"},
    {"prompt_id": "qq-002", "prompt": "What is 123456 * 789?", "expected_contains": ["97", "406", "784"], "scenario_id": "math_precision", "max_tokens": 100, "category": "math"},
    {"prompt_id": "qq-003", "prompt": "Solve: If 3x + 7 = 22, what is x?", "expected_contains": ["5"], "scenario_id": "math_precision", "max_tokens": 150, "category": "math"},
    {"prompt_id": "qq-004", "prompt": "What is the derivative of x^3 + 2x^2 - 5x + 1?", "expected_contains": ["3x", "4x", "5"], "scenario_id": "math_precision", "max_tokens": 150, "category": "math"},
    {"prompt_id": "qq-005", "prompt": "Calculate the area of a circle with radius 7. Use pi = 3.14159.", "expected_contains": ["153", "154"], "scenario_id": "math_precision", "max_tokens": 150, "category": "math"},

    # Reasoning (quantization quality check)
    {"prompt_id": "qq-006", "prompt": "A bat and ball cost $1.10 total. The bat costs $1.00 more than the ball. How much does the ball cost?", "expected_contains": ["0.05", "5 cents", "five cents"], "scenario_id": "reasoning", "max_tokens": 200, "category": "reasoning"},
    {"prompt_id": "qq-007", "prompt": "If all roses are flowers and some flowers fade quickly, can we conclude that some roses fade quickly?", "expected_contains": ["no", "cannot", "not necessarily"], "scenario_id": "reasoning", "max_tokens": 200, "category": "reasoning"},
    {"prompt_id": "qq-008", "prompt": "Three people check into a hotel room that costs $30. They each pay $10. Later the manager realizes it should be $25 and gives $5 to the bellboy to return. The bellboy keeps $2 and gives $1 back to each person. Now each person paid $9 (total $27) and the bellboy has $2 ($29). Where is the missing dollar?", "expected_contains": ["no missing", "fallacy", "error", "misleading"], "scenario_id": "reasoning", "max_tokens": 300, "category": "reasoning"},
    {"prompt_id": "qq-009", "prompt": "In a race, you overtake the person in 2nd place. What position are you now in?", "expected_contains": ["2nd", "second"], "scenario_id": "reasoning", "max_tokens": 150, "category": "reasoning"},
    {"prompt_id": "qq-010", "prompt": "If you have 6 apples and take away 4, how many do you have?", "expected_contains": ["4"], "scenario_id": "reasoning", "max_tokens": 100, "category": "reasoning"},

    # Code generation (precision-sensitive)
    {"prompt_id": "qq-011", "prompt": "Write a Python function to calculate fibonacci(n) recursively.", "expected_contains": ["def", "fibonacci", "return"], "scenario_id": "code_gen", "max_tokens": 200, "category": "code"},
    {"prompt_id": "qq-012", "prompt": "Write a Python function to check if a string is a palindrome.", "expected_contains": ["def", "palindrome", "return"], "scenario_id": "code_gen", "max_tokens": 200, "category": "code"},
    {"prompt_id": "qq-013", "prompt": "Write a SQL query to find the top 5 customers by total order value.", "expected_contains": ["SELECT", "ORDER BY", "LIMIT"], "scenario_id": "code_gen", "max_tokens": 200, "category": "code"},
    {"prompt_id": "qq-014", "prompt": "Write a Python function to merge two sorted lists.", "expected_contains": ["def", "merge", "return"], "scenario_id": "code_gen", "max_tokens": 250, "category": "code"},
    {"prompt_id": "qq-015", "prompt": "Write a binary search function in Python.", "expected_contains": ["def", "binary", "return"], "scenario_id": "code_gen", "max_tokens": 250, "category": "code"},

    # Factual knowledge
    {"prompt_id": "qq-016", "prompt": "What are the three laws of thermodynamics?", "expected_contains": ["energy", "entropy"], "scenario_id": "knowledge", "max_tokens": 300, "category": "science"},
    {"prompt_id": "qq-017", "prompt": "Explain the difference between mitosis and meiosis.", "expected_contains": ["cell", "division"], "scenario_id": "knowledge", "max_tokens": 300, "category": "science"},
    {"prompt_id": "qq-018", "prompt": "What causes the seasons on Earth?", "expected_contains": ["tilt", "axis"], "scenario_id": "knowledge", "max_tokens": 200, "category": "science"},
    {"prompt_id": "qq-019", "prompt": "Describe the process of photosynthesis.", "expected_contains": ["light", "carbon dioxide", "oxygen"], "scenario_id": "knowledge", "max_tokens": 300, "category": "science"},
    {"prompt_id": "qq-020", "prompt": "What is the difference between a virus and a bacterium?", "expected_contains": ["cell", "reproduce"], "scenario_id": "knowledge", "max_tokens": 300, "category": "science"},

    # Language / NLP tasks
    {"prompt_id": "qq-021", "prompt": "Translate 'The weather is beautiful today' to French.", "expected_contains": ["beau", "aujourd'hui", "temps"], "scenario_id": "translation", "max_tokens": 100, "category": "language"},
    {"prompt_id": "qq-022", "prompt": "Summarize the concept of supply and demand in exactly two sentences.", "expected_contains": ["supply", "demand", "price"], "scenario_id": "summarization", "max_tokens": 150, "category": "language"},
    {"prompt_id": "qq-023", "prompt": "Identify the sentiment of: 'I absolutely loved the movie, it was fantastic!'", "expected_contains": ["positive"], "scenario_id": "sentiment", "max_tokens": 100, "category": "language"},
    {"prompt_id": "qq-024", "prompt": "Paraphrase: 'Machine learning models learn patterns from data.'", "expected_contains": ["pattern", "data", "learn"], "scenario_id": "paraphrase", "max_tokens": 100, "category": "language"},
    {"prompt_id": "qq-025", "prompt": "Extract the named entities from: 'Barack Obama was born in Honolulu, Hawaii on August 4, 1961.'", "expected_contains": ["Obama", "Honolulu", "Hawaii"], "scenario_id": "ner", "max_tokens": 150, "category": "language"},

    # Long-form stress prompts
    {"prompt_id": "qq-026", "prompt": "Explain the observer pattern in software design with a Python example.", "expected_contains": ["class", "notify", "observer"], "scenario_id": "stress", "max_tokens": 500, "category": "code"},
    {"prompt_id": "qq-027", "prompt": "Compare and contrast TCP and UDP protocols. Include use cases for each.", "expected_contains": ["reliable", "connection", "UDP"], "scenario_id": "stress", "max_tokens": 400, "category": "networking"},
    {"prompt_id": "qq-028", "prompt": "Explain how a hash table works, including collision resolution strategies.", "expected_contains": ["hash", "collision", "bucket"], "scenario_id": "stress", "max_tokens": 400, "category": "cs"},
    {"prompt_id": "qq-029", "prompt": "Describe the CAP theorem and its implications for distributed databases.", "expected_contains": ["consistency", "availability", "partition"], "scenario_id": "stress", "max_tokens": 400, "category": "cs"},
    {"prompt_id": "qq-030", "prompt": "Explain how transformers work in NLP, including self-attention.", "expected_contains": ["attention", "query", "key"], "scenario_id": "stress", "max_tokens": 500, "category": "ml"},
]


# --------------- Finetune Domain Prompts (LoRA domain adaptation) ---------------
FINETUNE_DOMAIN_PROMPTS = [
    # Medical domain
    {"prompt_id": "ft-001", "prompt": "What is the first-line treatment for type 2 diabetes?", "expected_contains": ["metformin"], "scenario_id": "medical", "max_tokens": 200, "category": "medical"},
    {"prompt_id": "ft-002", "prompt": "What are the symptoms of myocardial infarction?", "expected_contains": ["chest", "pain"], "scenario_id": "medical", "max_tokens": 200, "category": "medical"},
    {"prompt_id": "ft-003", "prompt": "Explain the difference between Type 1 and Type 2 diabetes.", "expected_contains": ["insulin"], "scenario_id": "medical", "max_tokens": 300, "category": "medical"},
    {"prompt_id": "ft-004", "prompt": "What are the stages of chronic kidney disease?", "expected_contains": ["GFR", "stage"], "scenario_id": "medical", "max_tokens": 300, "category": "medical"},
    {"prompt_id": "ft-005", "prompt": "Describe the mechanism of action of ACE inhibitors.", "expected_contains": ["angiotensin", "enzyme"], "scenario_id": "medical", "max_tokens": 250, "category": "medical"},
    {"prompt_id": "ft-006", "prompt": "What is the Glasgow Coma Scale and how is it used?", "expected_contains": ["eye", "verbal", "motor"], "scenario_id": "medical", "max_tokens": 300, "category": "medical"},
    {"prompt_id": "ft-007", "prompt": "List the warning signs of a stroke using the FAST acronym.", "expected_contains": ["face", "arm", "speech", "time"], "scenario_id": "medical", "max_tokens": 200, "category": "medical"},
    {"prompt_id": "ft-008", "prompt": "What are common side effects of statin medications?", "expected_contains": ["muscle"], "scenario_id": "medical", "max_tokens": 200, "category": "medical"},
    {"prompt_id": "ft-009", "prompt": "Explain what an A1C test measures and normal ranges.", "expected_contains": ["hemoglobin", "blood sugar", "glucose"], "scenario_id": "medical", "max_tokens": 200, "category": "medical"},
    {"prompt_id": "ft-010", "prompt": "What is the difference between an MRI and CT scan?", "expected_contains": ["magnetic", "radiation"], "scenario_id": "medical", "max_tokens": 300, "category": "medical"},

    # Legal domain
    {"prompt_id": "ft-011", "prompt": "What is the difference between civil and criminal law?", "expected_contains": ["civil", "criminal"], "scenario_id": "legal", "max_tokens": 300, "category": "legal"},
    {"prompt_id": "ft-012", "prompt": "Explain the concept of habeas corpus.", "expected_contains": ["detention", "court", "unlawful"], "scenario_id": "legal", "max_tokens": 200, "category": "legal"},
    {"prompt_id": "ft-013", "prompt": "What is the doctrine of stare decisis?", "expected_contains": ["precedent"], "scenario_id": "legal", "max_tokens": 200, "category": "legal"},
    {"prompt_id": "ft-014", "prompt": "Define 'burden of proof' in a legal context.", "expected_contains": ["evidence", "prove"], "scenario_id": "legal", "max_tokens": 200, "category": "legal"},
    {"prompt_id": "ft-015", "prompt": "What are the elements of a valid contract?", "expected_contains": ["offer", "acceptance", "consideration"], "scenario_id": "legal", "max_tokens": 300, "category": "legal"},
    {"prompt_id": "ft-016", "prompt": "Explain the difference between a felony and a misdemeanor.", "expected_contains": ["serious", "punishment"], "scenario_id": "legal", "max_tokens": 200, "category": "legal"},
    {"prompt_id": "ft-017", "prompt": "What is the Miranda warning and when must it be given?", "expected_contains": ["right", "silent", "attorney"], "scenario_id": "legal", "max_tokens": 250, "category": "legal"},
    {"prompt_id": "ft-018", "prompt": "Define 'tort' in legal terms and give an example.", "expected_contains": ["harm", "civil", "wrong"], "scenario_id": "legal", "max_tokens": 200, "category": "legal"},
    {"prompt_id": "ft-019", "prompt": "What is the difference between patent and copyright?", "expected_contains": ["invention", "original work", "protect"], "scenario_id": "legal", "max_tokens": 300, "category": "legal"},
    {"prompt_id": "ft-020", "prompt": "Explain what 'due process' means under the 14th Amendment.", "expected_contains": ["fair", "law", "rights"], "scenario_id": "legal", "max_tokens": 250, "category": "legal"},

    # Code/technical domain
    {"prompt_id": "ft-021", "prompt": "Explain Kubernetes pod scheduling and affinity rules.", "expected_contains": ["node", "affinity", "schedule"], "scenario_id": "technical", "max_tokens": 400, "category": "code"},
    {"prompt_id": "ft-022", "prompt": "Describe how a B-tree index works in a database.", "expected_contains": ["tree", "node", "key"], "scenario_id": "technical", "max_tokens": 400, "category": "code"},
    {"prompt_id": "ft-023", "prompt": "Explain the difference between optimistic and pessimistic concurrency control.", "expected_contains": ["lock", "conflict", "transaction"], "scenario_id": "technical", "max_tokens": 300, "category": "code"},
    {"prompt_id": "ft-024", "prompt": "Describe the Raft consensus algorithm.", "expected_contains": ["leader", "election", "log"], "scenario_id": "technical", "max_tokens": 400, "category": "code"},
    {"prompt_id": "ft-025", "prompt": "Explain how gRPC differs from REST APIs.", "expected_contains": ["protocol buffer", "HTTP/2", "binary"], "scenario_id": "technical", "max_tokens": 300, "category": "code"},

    # General knowledge regression check
    {"prompt_id": "ft-026", "prompt": "What is 15 * 17?", "expected_contains": ["255"], "scenario_id": "regression", "max_tokens": 50, "category": "math"},
    {"prompt_id": "ft-027", "prompt": "What is the capital of Japan?", "expected_contains": ["Tokyo"], "scenario_id": "regression", "max_tokens": 50, "category": "knowledge"},
    {"prompt_id": "ft-028", "prompt": "Who discovered penicillin?", "expected_contains": ["Fleming"], "scenario_id": "regression", "max_tokens": 100, "category": "knowledge"},
    {"prompt_id": "ft-029", "prompt": "What year did the Berlin Wall fall?", "expected_contains": ["1989"], "scenario_id": "regression", "max_tokens": 50, "category": "knowledge"},
    {"prompt_id": "ft-030", "prompt": "What is the chemical formula for glucose?", "expected_contains": ["C6H12O6"], "scenario_id": "regression", "max_tokens": 100, "category": "knowledge"},
]


# --------------- Eval Calibration Prompts (Judge scoring validation) ---------------
EVAL_CALIBRATION_PROMPTS = [
    # Good responses (expect high scores)
    {"prompt_id": "ec-001", "prompt": "What is machine learning?", "expected_contains": ["data", "learn", "model"], "scenario_id": "calibration-good", "max_tokens": 200, "category": "good_response"},
    {"prompt_id": "ec-002", "prompt": "Explain photosynthesis.", "expected_contains": ["light", "plant", "energy"], "scenario_id": "calibration-good", "max_tokens": 200, "category": "good_response"},
    {"prompt_id": "ec-003", "prompt": "What is the theory of relativity?", "expected_contains": ["Einstein", "energy", "mass"], "scenario_id": "calibration-good", "max_tokens": 300, "category": "good_response"},
    {"prompt_id": "ec-004", "prompt": "How does encryption work?", "expected_contains": ["key", "encrypt", "decrypt"], "scenario_id": "calibration-good", "max_tokens": 300, "category": "good_response"},
    {"prompt_id": "ec-005", "prompt": "Explain how vaccines work.", "expected_contains": ["immune", "antibod"], "scenario_id": "calibration-good", "max_tokens": 300, "category": "good_response"},
    {"prompt_id": "ec-006", "prompt": "What is DNA and why is it important?", "expected_contains": ["genetic", "nucleic"], "scenario_id": "calibration-good", "max_tokens": 300, "category": "good_response"},
    {"prompt_id": "ec-007", "prompt": "Describe how the internet works.", "expected_contains": ["network", "protocol", "data"], "scenario_id": "calibration-good", "max_tokens": 400, "category": "good_response"},
    {"prompt_id": "ec-008", "prompt": "Explain the water cycle.", "expected_contains": ["evaporation", "condensation", "precipitation"], "scenario_id": "calibration-good", "max_tokens": 300, "category": "good_response"},
    {"prompt_id": "ec-009", "prompt": "What is artificial intelligence?", "expected_contains": ["machine", "intelligence", "human"], "scenario_id": "calibration-good", "max_tokens": 200, "category": "good_response"},
    {"prompt_id": "ec-010", "prompt": "Explain how a CPU works.", "expected_contains": ["instruction", "process", "arithmetic"], "scenario_id": "calibration-good", "max_tokens": 300, "category": "good_response"},

    # Ambiguous / tricky prompts (test judge nuance)
    {"prompt_id": "ec-011", "prompt": "Is AI dangerous?", "expected_contains": ["risk", "benefit"], "scenario_id": "calibration-ambiguous", "max_tokens": 300, "category": "ambiguous"},
    {"prompt_id": "ec-012", "prompt": "Should we colonize Mars?", "expected_contains": ["resource", "challenge"], "scenario_id": "calibration-ambiguous", "max_tokens": 300, "category": "ambiguous"},
    {"prompt_id": "ec-013", "prompt": "Is social media good or bad for society?", "expected_contains": ["connect", "mental"], "scenario_id": "calibration-ambiguous", "max_tokens": 300, "category": "ambiguous"},
    {"prompt_id": "ec-014", "prompt": "Will AI replace programmers?", "expected_contains": ["tool", "augment"], "scenario_id": "calibration-ambiguous", "max_tokens": 300, "category": "ambiguous"},
    {"prompt_id": "ec-015", "prompt": "Is nuclear energy safe?", "expected_contains": ["risk", "benefit", "radiation"], "scenario_id": "calibration-ambiguous", "max_tokens": 300, "category": "ambiguous"},

    # Factual accuracy tests (verifiable answers)
    {"prompt_id": "ec-016", "prompt": "How many planets are in our solar system?", "expected_contains": ["8", "eight"], "scenario_id": "calibration-factual", "max_tokens": 100, "category": "factual"},
    {"prompt_id": "ec-017", "prompt": "What is the speed of light?", "expected_contains": ["299", "300"], "scenario_id": "calibration-factual", "max_tokens": 100, "category": "factual"},
    {"prompt_id": "ec-018", "prompt": "Who wrote 'To Kill a Mockingbird'?", "expected_contains": ["Harper Lee"], "scenario_id": "calibration-factual", "max_tokens": 100, "category": "factual"},
    {"prompt_id": "ec-019", "prompt": "What is the atomic number of carbon?", "expected_contains": ["6"], "scenario_id": "calibration-factual", "max_tokens": 100, "category": "factual"},
    {"prompt_id": "ec-020", "prompt": "What year was the Declaration of Independence signed?", "expected_contains": ["1776"], "scenario_id": "calibration-factual", "max_tokens": 100, "category": "factual"},
]


def main():
    parser = argparse.ArgumentParser(description="Generate promptsets for LLM Platform")
    parser.add_argument("--output-dir", default="data/promptsets", help="Output directory")
    args = parser.parse_args()

    output_base = Path(args.output_dir)
    gen = PromptsetGenerator(seed=42)

    # --- Canary promptset ---
    canary_dir = output_base / "canary"
    canary_dir.mkdir(parents=True, exist_ok=True)
    canary_manifest = gen.generate_promptset(
        scenario_id="canary-v1",
        dataset_id="canary-deployment-health",
        prompts=[{**p, "target_output_tokens": p.get("max_tokens", 50)} for p in CANARY_PROMPTS],
        output_dir=canary_dir,
    )
    print(f"[canary]       {canary_manifest.prompt_count} prompts -> {canary_dir}")

    # --- Performance promptset ---
    perf_dir = output_base / "performance"
    perf_dir.mkdir(parents=True, exist_ok=True)
    perf_manifest = gen.generate_promptset(
        scenario_id="performance-v1",
        dataset_id="performance-throughput",
        prompts=[{**p, "target_output_tokens": p.get("target_output_tokens", 50)} for p in PERFORMANCE_PROMPTS],
        output_dir=perf_dir,
    )
    print(f"[performance]  {perf_manifest.prompt_count} prompts -> {perf_dir}")

    # --- Quant-quality promptset (AWQ vs FP16 comparison) ---
    quant_dir = output_base / "quant-quality"
    quant_dir.mkdir(parents=True, exist_ok=True)
    quant_manifest = gen.generate_promptset(
        scenario_id="quant-quality-v1",
        dataset_id="quant-quality",
        prompts=[{**p, "target_output_tokens": p.get("max_tokens", 100)} for p in QUANT_QUALITY_PROMPTS],
        output_dir=quant_dir,
    )
    print(f"[quant-quality] {quant_manifest.prompt_count} prompts -> {quant_dir}")

    # --- Finetune-domain promptset (LoRA domain adaptation) ---
    ft_dir = output_base / "finetune-domain"
    ft_dir.mkdir(parents=True, exist_ok=True)
    ft_manifest = gen.generate_promptset(
        scenario_id="finetune-domain-v1",
        dataset_id="finetune-domain",
        prompts=[{**p, "target_output_tokens": p.get("max_tokens", 200)} for p in FINETUNE_DOMAIN_PROMPTS],
        output_dir=ft_dir,
    )
    print(f"[finetune-domain] {ft_manifest.prompt_count} prompts -> {ft_dir}")

    # --- Eval-calibration promptset (judge scoring validation) ---
    eval_dir = output_base / "eval-calibration"
    eval_dir.mkdir(parents=True, exist_ok=True)
    eval_manifest = gen.generate_promptset(
        scenario_id="eval-calibration-v1",
        dataset_id="eval-calibration",
        prompts=[{**p, "target_output_tokens": p.get("max_tokens", 100)} for p in EVAL_CALIBRATION_PROMPTS],
        output_dir=eval_dir,
    )
    print(f"[eval-calibration] {eval_manifest.prompt_count} prompts -> {eval_dir}")

    print("\nDone. Run the harness with:")
    print(f"  python services/test-harness/harness.py \\")
    print(f"    --promptset {canary_dir}/promptset.jsonl \\")
    print(f"    --gateway http://localhost:8000 \\")
    print(f"    --team quant --concurrency 5")


if __name__ == "__main__":
    main()

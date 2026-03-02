#!/usr/bin/env python3
"""Generate benchmark promptsets for the LLM Optimization Platform.

Produces 3 team-specific benchmark promptsets (700 total prompts):
  benchmark-quant:    250 prompts (AWQ vs FP16 quality comparison)
  benchmark-finetune: 250 prompts (LoRA domain adaptation testing)
  benchmark-eval:     200 prompts (Judge model scoring calibration)

Usage:
    python scripts/generate-benchmark.py [--output-dir data/promptsets]
"""

import sys
import os
import random
import argparse
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'services', 'data-engine'))
from generator import PromptsetGenerator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def expand(tuples, prefix, scenario_id, category, default_max=200):
    """Convert compact (prompt, expected, max_tokens) tuples to prompt dicts."""
    out = []
    for i, t in enumerate(tuples):
        text = t[0]
        expected = t[1] if len(t) > 1 else None
        max_tok = t[2] if len(t) > 2 else default_max
        out.append({
            "prompt_id": f"{prefix}-{i+1:03d}",
            "prompt": text,
            "expected_contains": expected,
            "scenario_id": scenario_id,
            "max_tokens": max_tok,
            "category": category,
        })
    return out


# ===================================================================
#  QUANT BENCHMARK  (250 prompts — AWQ vs FP16 quality comparison)
# ===================================================================

def _quant_math(rng):
    """Generate 50 math precision prompts programmatically."""
    prompts = []
    # 10 multiplication
    for _ in range(10):
        a, b = rng.randint(10, 99), rng.randint(10, 99)
        prompts.append((f"Calculate {a} * {b}.", [str(a * b)], 100))
    # 10 powers
    for _ in range(10):
        base, exp = rng.randint(2, 9), rng.randint(2, 5)
        prompts.append((f"What is {base}^{exp}?", [str(base ** exp)], 100))
    # 10 division
    for _ in range(10):
        a = rng.randint(100, 999)
        b = rng.randint(2, 20)
        q = a // b
        prompts.append((f"What is {a} divided by {b}? Give the integer part.", [str(q)], 100))
    # 10 percentages
    for _ in range(10):
        pct = rng.choice([10, 15, 20, 25, 30, 40, 50, 60, 75, 80])
        val = rng.randint(50, 500) * 2  # ensure even for clean results
        answer = pct * val // 100
        prompts.append((f"What is {pct}% of {val}?", [str(answer)], 100))
    # 10 multi-step
    for _ in range(10):
        a, b, c = rng.randint(2, 20), rng.randint(2, 20), rng.randint(2, 20)
        prompts.append((f"Calculate ({a} + {b}) * {c}.", [str((a + b) * c)], 100))
    return prompts


QUANT_REASONING = [
    ("A bat and ball cost $1.10 total. The bat costs $1 more than the ball. How much does the ball cost?", ["0.05", "5 cents", "five cents"], 200),
    ("If all roses are flowers and some flowers fade quickly, can we conclude some roses fade quickly?", ["no", "cannot", "not necessarily"], 200),
    ("In a race you overtake the person in 2nd place. What position are you now in?", ["2nd", "second"], 150),
    ("If you have 6 apples and take away 4, how many do you have?", ["4"], 100),
    ("A farmer has 17 sheep. All but 9 die. How many are left?", ["9"], 100),
    ("How many times can you subtract 5 from 25?", ["once", "1", "one time"], 150),
    ("If a doctor gives you 3 pills and says take one every 30 minutes, how long do they last?", ["60", "1 hour", "one hour"], 150),
    ("Is it legal for a man to marry his widow's sister?", ["no", "dead", "cannot"], 150),
    ("If there are 3 apples and you take away 2, how many apples do YOU have?", ["2"], 100),
    ("A clerk at a butcher shop is 5 ft 10 in tall. What does he weigh?", ["meat"], 150),
    ("If you rearrange the letters CIFAIPC, you get the name of a(n)?", ["ocean", "Pacific"], 100),
    ("Before Mount Everest was discovered, what was the tallest mountain on Earth?", ["Everest", "still"], 200),
    ("Some months have 30 days, some have 31. How many months have 28 days?", ["12", "all", "every"], 150),
    ("A train leaves at 9am going 60mph. Another leaves at 10am going 80mph. When does the second catch the first?", ["1", "pm", "noon"], 300),
    ("You are in a dark room with a candle, a wood stove, and a gas lamp. You only have one match. What do you light first?", ["match"], 150),
    ("How far can a dog run into the woods?", ["halfway", "half"], 100),
    ("If 2 is company and 3 is a crowd, what are 4 and 5?", ["9", "nine"], 100),
    ("Why are 1968 pennies worth more than 1967 pennies?", ["one more", "extra", "1968"], 200),
    ("What weighs more, a pound of feathers or a pound of bricks?", ["same", "equal", "neither"], 150),
    ("If a plane crashes on the border of US and Canada, where do you bury the survivors?", ["don't", "alive", "survivors"], 150),
    ("Three people each order a pizza. The waiter brings 3. How many pizzas are there?", ["3", "three"], 100),
    ("What comes next: 2, 6, 12, 20, 30, ?", ["42"], 150),
    ("What comes next: 1, 1, 2, 3, 5, 8, ?", ["13"], 100),
    ("If you have a 3-gallon jug and a 5-gallon jug, how do you measure 4 gallons?", ["fill", "pour"], 300),
    ("You see a boat filled with people but there is not a single person on board. How?", ["married", "couples", "all married"], 150),
    ("A man builds a house with all 4 sides facing south. A bear walks by. What color is the bear?", ["white", "polar"], 150),
    ("I speak without a mouth and hear without ears. I have no body, but I come alive with the wind. What am I?", ["echo"], 100),
    ("What has keys but no locks, space but no room, you can enter but can't go inside?", ["keyboard"], 100),
    ("What has a head and a tail but no body?", ["coin"], 100),
    ("The more you take, the more you leave behind. What am I?", ["footsteps", "steps"], 100),
    ("What has cities but no houses, forests but no trees, water but no fish?", ["map"], 100),
    ("If two's company and three's a crowd, what is four and five?", ["9", "nine"], 100),
    ("A cowboy rides into town on Friday. He stays 3 days and leaves on Friday. How?", ["horse", "named Friday"], 200),
    ("What gets wetter the more it dries?", ["towel"], 100),
    ("What can travel around the world while staying in a corner?", ["stamp"], 100),
    ("If 5 machines take 5 minutes to make 5 widgets, how long for 100 machines to make 100 widgets?", ["5"], 200),
    ("There are 5 houses in 5 colors. The English person lives in the red house. Who owns the fish?", ["German"], 400),
    ("A woman shoots her husband, then holds him under water for 5 minutes. Then she hangs him. But 5 minutes later they enjoy dinner. How?", ["photograph", "picture", "photo"], 200),
    ("What occurs once in a minute, twice in a moment, but never in a thousand years?", ["m", "letter"], 100),
    ("I am not alive but I grow. I have no lungs but I need air. What am I?", ["fire"], 100),
    ("What can be broken without being held?", ["promise"], 100),
    ("Complete the pattern: 1, 4, 9, 16, 25, ?", ["36"], 100),
    ("Complete the pattern: 2, 3, 5, 7, 11, 13, ?", ["17"], 100),
    ("If you multiply all digits from 0-9, what is the result?", ["0", "zero"], 100),
    ("What is the next prime number after 97?", ["101"], 100),
    ("A lily pad doubles in size each day. On day 48 it covers the lake. On what day was it half covered?", ["47"], 150),
    ("You have 12 balls, one is heavier. With a balance scale, what is the minimum weighings to find it?", ["3", "three"], 200),
    ("How many squares are on a standard 8x8 chessboard?", ["204"], 200),
    ("What is the sum of integers from 1 to 100?", ["5050"], 100),
    ("If you flip a fair coin 3 times, what is the probability of getting exactly 2 heads?", ["3/8", "0.375", "37.5"], 200),
]

QUANT_CODE = [
    ("Write a Python function to compute factorial(n) iteratively.", ["def", "factorial", "return"], 200),
    ("Write a Python function to check if a number is prime.", ["def", "prime", "return"], 200),
    ("Write a Python function to reverse a linked list.", ["def", "next", "return"], 300),
    ("Write a Python function to find the GCD of two numbers.", ["def", "gcd", "return"], 200),
    ("Write a Python function to implement binary search.", ["def", "binary", "return"], 250),
    ("Write a Python function to merge two sorted lists.", ["def", "merge", "return"], 250),
    ("Write a Python function to check if a string is a palindrome.", ["def", "palindrome", "return"], 200),
    ("Write a Python function to flatten a nested list.", ["def", "flatten", "return"], 250),
    ("Write a Python function to compute the nth Fibonacci number using memoization.", ["def", "fib", "return"], 250),
    ("Write a Python function to find all permutations of a string.", ["def", "perm", "return"], 300),
    ("Write a SQL query to find the top 5 customers by total order amount.", ["SELECT", "ORDER BY", "LIMIT"], 200),
    ("Write a SQL query to find duplicate email addresses in a users table.", ["SELECT", "GROUP BY", "HAVING"], 200),
    ("Write a SQL query joining orders with customers where order total exceeds 1000.", ["SELECT", "JOIN", "WHERE"], 200),
    ("Write a SQL query to find the second-highest salary.", ["SELECT", "salary"], 200),
    ("Write a SQL query to calculate a running total of daily sales.", ["SELECT", "SUM", "OVER"], 200),
    ("Write a Python class implementing a stack with push, pop, and peek.", ["class", "push", "pop"], 300),
    ("Write a Python class implementing a queue using two stacks.", ["class", "enqueue", "dequeue"], 300),
    ("Write a Python function for depth-first search on a graph.", ["def", "dfs", "visited"], 300),
    ("Write a Python function for breadth-first search on a graph.", ["def", "bfs", "queue"], 300),
    ("Write a Python function to find the longest common substring of two strings.", ["def", "common", "return"], 300),
    ("Write a Python decorator that logs function execution time.", ["def", "wrapper", "time"], 250),
    ("Write a Python function to validate an email address using regex.", ["def", "re", "return"], 200),
    ("Write a Python function to read a CSV file and return a list of dicts.", ["def", "csv", "return"], 250),
    ("Write a Python context manager for database connections.", ["class", "__enter__", "__exit__"], 300),
    ("Write a Python async function that fetches a URL with aiohttp.", ["async", "def", "await"], 250),
    ("Write a Python function to implement quicksort.", ["def", "quicksort", "pivot"], 300),
    ("Write a Python function to implement mergesort.", ["def", "mergesort", "merge"], 300),
    ("Write a Python function to detect a cycle in a linked list.", ["def", "cycle", "return"], 250),
    ("Write a Python function to find the kth largest element in an array.", ["def", "return"], 250),
    ("Write a Python function to implement a trie data structure insert and search.", ["class", "insert", "search"], 400),
    ("Write a Python function to serialize and deserialize a binary tree.", ["def", "serialize", "deserialize"], 400),
    ("Write a Python function to find the longest increasing subsequence.", ["def", "longest", "return"], 300),
    ("Write a Python generator that yields prime numbers.", ["def", "yield", "prime"], 250),
    ("Write a Python function to implement LRU cache.", ["class", "get", "put"], 400),
    ("Write a Python function to validate balanced parentheses.", ["def", "stack", "return"], 200),
    ("Write a Python function to convert Roman numerals to integers.", ["def", "roman", "return"], 300),
    ("Write a Python function to implement matrix multiplication.", ["def", "matrix", "return"], 300),
    ("Write a Python function to find all anagrams of a word in a list.", ["def", "anagram", "return"], 250),
    ("Write a Python function to implement Dijkstra's shortest path.", ["def", "dijkstra", "distance"], 400),
    ("Write a Python function to implement a min-heap.", ["class", "insert", "extract"], 400),
    ("Write a Bash one-liner to find the 10 largest files in /var/log.", ["find", "sort", "head"], 150),
    ("Write a Python function to count word frequencies in a text.", ["def", "count", "return"], 200),
    ("Write a Python function to convert a decimal to binary.", ["def", "binary", "return"], 200),
    ("Write a Python function to implement the Sieve of Eratosthenes.", ["def", "sieve", "prime"], 250),
    ("Write a Python function to check if two strings are anagrams.", ["def", "anagram", "return"], 200),
    ("Write a Python function to rotate a matrix 90 degrees clockwise.", ["def", "rotate", "matrix"], 300),
    ("Write a Python function to find the median of two sorted arrays.", ["def", "median", "return"], 300),
    ("Write a Python function to implement a bloom filter.", ["class", "add", "contains"], 400),
    ("Write a Python function to parse a JSON string without using json module.", ["def", "parse", "return"], 400),
    ("Write a Python function to calculate Levenshtein distance.", ["def", "distance", "return"], 300),
]

QUANT_FACTUAL = [
    ("What is the chemical symbol for gold?", ["Au"], 50),
    ("What planet is closest to the Sun?", ["Mercury"], 50),
    ("What is the speed of light in meters per second?", ["299792458", "3", "10^8"], 100),
    ("Who wrote Romeo and Juliet?", ["Shakespeare"], 50),
    ("What is the largest ocean on Earth?", ["Pacific"], 50),
    ("What year did World War II end?", ["1945"], 50),
    ("What is the powerhouse of the cell?", ["mitochondria"], 50),
    ("What is the atomic number of carbon?", ["6"], 50),
    ("What is the smallest prime number?", ["2"], 50),
    ("Who painted the Mona Lisa?", ["Leonardo", "Vinci"], 50),
    ("What is the capital of Australia?", ["Canberra"], 50),
    ("What is the half-life of Carbon-14?", ["5730", "5700"], 100),
    ("What is Avogadro's number?", ["6.022", "10^23"], 100),
    ("What is the boiling point of water in Celsius?", ["100"], 50),
    ("What is the PH of pure water?", ["7"], 50),
    ("What gas do plants absorb from the atmosphere?", ["CO2", "carbon dioxide"], 50),
    ("What is the most abundant element in the universe?", ["hydrogen"], 50),
    ("Who developed the theory of general relativity?", ["Einstein"], 50),
    ("What is the SI unit of electric current?", ["ampere", "amp"], 50),
    ("What is the charge of an electron?", ["negative", "-1.6"], 100),
    ("Who discovered penicillin?", ["Fleming"], 50),
    ("What is the formula for the area of a circle?", ["pi", "r^2", "r**2"], 100),
    ("What is the longest river in the world?", ["Nile", "Amazon"], 50),
    ("What is the largest desert in the world?", ["Sahara", "Antarctic"], 100),
    ("Who invented the telephone?", ["Bell"], 50),
    ("What is the freezing point of water in Fahrenheit?", ["32"], 50),
    ("What is the molecular formula for glucose?", ["C6H12O6"], 100),
    ("What element has the symbol Fe?", ["iron"], 50),
    ("How many chromosomes do humans have?", ["46"], 50),
    ("What is the distance from Earth to the Moon in kilometers?", ["384", "400"], 100),
    ("What is the tallest animal in the world?", ["giraffe"], 50),
    ("What year was the Declaration of Independence signed?", ["1776"], 50),
    ("What is the chemical formula for table salt?", ["NaCl"], 50),
    ("What is the most abundant gas in Earth's atmosphere?", ["nitrogen"], 50),
    ("What is the largest organ in the human body?", ["skin"], 50),
    ("What is absolute zero in Celsius?", ["-273", "273.15"], 100),
    ("What is the Pythagorean theorem?", ["a^2", "b^2", "c^2"], 100),
    ("How many bones are in the adult human body?", ["206"], 50),
    ("What is the speed of sound in air at sea level?", ["343", "340"], 100),
    ("What planet has the most moons?", ["Saturn", "Jupiter"], 50),
    ("What is the chemical symbol for sodium?", ["Na"], 50),
    ("What is the process by which plants make food from sunlight?", ["photosynthesis"], 50),
    ("What is the hardest natural substance?", ["diamond"], 50),
    ("What is the largest planet in our solar system?", ["Jupiter"], 50),
    ("What is DNA an abbreviation for?", ["deoxyribonucleic"], 100),
    ("What is the currency of Japan?", ["yen"], 50),
    ("Who was the first person to walk on the Moon?", ["Armstrong", "Neil"], 50),
    ("What is the main component of the Sun?", ["hydrogen", "helium"], 50),
    ("What is the acceleration due to gravity on Earth?", ["9.8", "9.81"], 100),
    ("How many elements are in the periodic table?", ["118"], 50),
]

QUANT_LONGFORM = [
    ("Explain how a neural network learns through backpropagation. Include the chain rule and gradient descent.", None, 500),
    ("Describe the water cycle in detail, covering evaporation, condensation, precipitation, and collection.", None, 400),
    ("Write a detailed comparison of TCP and UDP protocols. Cover reliability, speed, and use cases.", None, 500),
    ("Explain the process of photosynthesis at the molecular level.", None, 400),
    ("Describe the architecture of a modern CPU including pipeline stages.", None, 500),
    ("Write a comprehensive overview of the causes of World War I.", None, 500),
    ("Explain how public-key cryptography works, including RSA.", None, 500),
    ("Describe the process of human digestion from mouth to intestine.", None, 400),
    ("Write a detailed explanation of how Docker containers work internally.", None, 500),
    ("Explain the economics of supply and demand with examples.", None, 400),
    ("Describe the theory of evolution by natural selection.", None, 500),
    ("Write a comprehensive guide to SQL JOINs with examples.", None, 500),
    ("Explain how a compiler transforms source code into machine code.", None, 500),
    ("Describe the greenhouse effect and its role in climate change.", None, 400),
    ("Write a detailed overview of HTTP/2 improvements over HTTP/1.1.", None, 500),
    ("Explain the CAP theorem in distributed systems with examples.", None, 500),
    ("Describe how vaccines work to provide immunity.", None, 400),
    ("Write a detailed explanation of Git branching strategies.", None, 500),
    ("Explain the difference between classical and quantum computing.", None, 500),
    ("Describe the electoral college system in the United States.", None, 400),
    ("Write a comprehensive overview of machine learning model evaluation metrics.", None, 500),
    ("Explain how DNS resolution works step by step.", None, 400),
    ("Describe the architecture of Kubernetes and its main components.", None, 500),
    ("Write a detailed comparison of NoSQL database types.", None, 500),
    ("Explain the principles of object-oriented programming.", None, 400),
    ("Describe how a blockchain achieves consensus.", None, 500),
    ("Write a comprehensive overview of RESTful API design principles.", None, 500),
    ("Explain the process of mitosis and meiosis in cell division.", None, 500),
    ("Describe how OAuth 2.0 authorization works.", None, 500),
    ("Write a detailed explanation of microservices architecture patterns.", None, 500),
    ("Explain the physics of how airplanes generate lift.", None, 400),
    ("Describe the differences between IPv4 and IPv6.", None, 400),
    ("Write a comprehensive overview of data normalization in databases.", None, 500),
    ("Explain how garbage collection works in programming languages.", None, 500),
    ("Describe the process of nuclear fission and fusion.", None, 500),
    ("Write a detailed guide to Prometheus metrics and alerting.", None, 500),
    ("Explain the principles behind load balancing algorithms.", None, 500),
    ("Describe how HTTPS and TLS handshake work.", None, 500),
    ("Write a comprehensive overview of design patterns: Singleton, Factory, Observer.", None, 500),
    ("Explain the MapReduce programming model with examples.", None, 500),
    ("Describe the structure and function of DNA replication.", None, 500),
    ("Write a detailed comparison of message queue systems: Kafka vs RabbitMQ.", None, 500),
    ("Explain how neural network attention mechanisms work in transformers.", None, 500),
    ("Describe the principles of ACID transactions in databases.", None, 400),
    ("Write a comprehensive overview of CI/CD best practices.", None, 500),
    ("Explain the concept of eventual consistency in distributed systems.", None, 400),
    ("Describe how WebSockets work compared to HTTP polling.", None, 400),
    ("Write a detailed explanation of container orchestration with Kubernetes.", None, 500),
    ("Explain the history and impact of Moore's Law.", None, 400),
    ("Describe the architecture of a modern web application from frontend to database.", None, 500),
]



# ===================================================================
#  FINETUNE BENCHMARK  (250 prompts — LoRA domain adaptation)
# ===================================================================

FINETUNE_MEDICAL = [
    ("What is the first-line treatment for type 2 diabetes?", ["metformin"], 200),
    ("Describe the pathophysiology of congestive heart failure.", ["heart", "pump", "fluid"], 400),
    ("What are the symptoms of myocardial infarction?", ["chest", "pain"], 200),
    ("Explain the mechanism of action of ACE inhibitors.", ["angiotensin", "enzyme"], 300),
    ("What are the stages of chronic kidney disease based on GFR?", ["GFR", "stage"], 300),
    ("Describe the Glasgow Coma Scale and its components.", ["eye", "verbal", "motor"], 300),
    ("List the warning signs of stroke using the FAST acronym.", ["face", "arm", "speech", "time"], 200),
    ("What are common side effects of statin medications?", ["muscle"], 200),
    ("Explain what an A1C test measures.", ["hemoglobin", "glucose"], 200),
    ("What is the difference between MRI and CT scan?", ["magnetic", "radiation"], 300),
    ("Describe the treatment protocol for anaphylaxis.", ["epinephrine", "adrenaline"], 300),
    ("What are the diagnostic criteria for metabolic syndrome?", ["waist", "blood pressure", "glucose"], 300),
    ("Explain the process of hemodialysis.", ["blood", "filter", "waste"], 300),
    ("What is the Child-Pugh score used for?", ["liver", "cirrhosis", "severity"], 300),
    ("Describe the ABCDE approach to trauma assessment.", ["airway", "breathing", "circulation"], 300),
    ("What are the classes of heart failure medications?", ["ACE", "beta", "diuretic"], 300),
    ("Explain the difference between Type 1 and Type 2 diabetes.", ["insulin", "autoimmune"], 300),
    ("What is the CURB-65 score in pneumonia?", ["confusion", "urea", "respiratory"], 300),
    ("Describe the mechanism of action of SSRIs.", ["serotonin", "reuptake"], 300),
    ("What are the indications for thrombolytic therapy?", ["clot", "stroke", "myocardial"], 300),
    ("Explain the TNM staging system for cancer.", ["tumor", "node", "metastasis"], 300),
    ("What are the components of the complete blood count (CBC)?", ["red", "white", "platelet"], 300),
    ("Describe the pathophysiology of asthma.", ["airway", "inflammation", "broncho"], 300),
    ("What is the Wells score used for?", ["DVT", "pulmonary", "embolism"], 300),
    ("Explain the difference between systolic and diastolic blood pressure.", ["contraction", "relaxation"], 300),
    ("What are the contraindications for MRI?", ["pacemaker", "metal", "implant"], 300),
    ("Describe the pharmacokinetics of insulin.", ["onset", "peak", "duration"], 300),
    ("What is the MELD score and what does it predict?", ["liver", "transplant"], 300),
    ("Explain the pathophysiology of sepsis.", ["infection", "immune", "organ"], 300),
    ("What are the normal ranges for arterial blood gas values?", ["pH", "pCO2", "HCO3"], 300),
    ("Describe the management of diabetic ketoacidosis.", ["insulin", "fluid", "potassium"], 300),
    ("What is the APGAR score and when is it assessed?", ["appearance", "pulse", "newborn"], 300),
    ("Explain the difference between Crohn's disease and ulcerative colitis.", ["Crohn", "colon", "inflammation"], 400),
    ("What are the risk factors for deep vein thrombosis?", ["immobility", "surgery", "cancer"], 300),
    ("Describe the mechanism of action of proton pump inhibitors.", ["acid", "pump", "stomach"], 300),
    ("What is the CAGE questionnaire used for?", ["alcohol", "screening"], 200),
    ("Explain the pathophysiology of myocardial infarction.", ["coronary", "plaque", "ischemia"], 400),
    ("What are the phases of a clinical trial?", ["phase", "safety", "efficacy"], 300),
    ("Describe the pathophysiology of pneumothorax.", ["lung", "air", "pleural"], 300),
    ("What is the purpose of a Holter monitor?", ["heart", "rhythm", "24"], 200),
    ("Explain the concept of antibiotic resistance.", ["bacteria", "resistant", "mutation"], 300),
    ("What are the signs and symptoms of hypothyroidism?", ["fatigue", "weight", "cold"], 300),
    ("Describe the management of acute coronary syndrome.", ["aspirin", "anticoagul", "catheter"], 400),
    ("What is the purpose of the Krebs cycle?", ["ATP", "energy", "electron"], 300),
    ("Explain the difference between osteoarthritis and rheumatoid arthritis.", ["degenerative", "autoimmune", "joint"], 300),
    ("What are the components of the SOFA score?", ["respiration", "coagulation", "liver"], 300),
    ("Describe the pathophysiology of acute kidney injury.", ["kidney", "creatinine", "GFR"], 300),
    ("What is the Ranson criteria used for?", ["pancreatitis", "severity"], 200),
    ("Explain the concept of herd immunity.", ["population", "immune", "threshold"], 300),
    ("What are the stages of wound healing?", ["hemostasis", "inflammation", "proliferation"], 300),
    ("Describe the management of status epilepticus.", ["benzodiazepine", "seizure", "airway"], 300),
    ("What is the purpose of cardiac catheterization?", ["coronary", "artery", "stent"], 300),
    ("Explain pharmacogenomics and its clinical applications.", ["genetic", "drug", "metabolism"], 300),
    ("What are the electrolyte abnormalities seen in renal failure?", ["potassium", "sodium", "calcium"], 300),
    ("Describe the mechanism of action of beta-blockers.", ["beta", "heart rate", "block"], 300),
    ("What is the Braden Scale used for?", ["pressure", "ulcer", "risk"], 200),
    ("Explain the pathophysiology of cirrhosis.", ["liver", "fibrosis", "scarring"], 300),
    ("What are the different types of shock?", ["hypovolemic", "cardiogenic", "septic"], 300),
    ("Describe the biosynthesis pathway of hemoglobin.", ["heme", "globin", "iron"], 300),
    ("What is the Duke criteria for infective endocarditis?", ["vegetation", "blood culture", "fever"], 300),
]

FINETUNE_LEGAL = [
    ("What is the difference between civil and criminal law?", ["civil", "criminal"], 300),
    ("Explain the concept of habeas corpus.", ["detention", "court", "unlawful"], 200),
    ("What is the doctrine of stare decisis?", ["precedent"], 200),
    ("Define burden of proof in a legal context.", ["evidence", "prove"], 200),
    ("What are the elements of a valid contract?", ["offer", "acceptance", "consideration"], 300),
    ("Explain the difference between a felony and a misdemeanor.", ["serious", "punishment"], 200),
    ("What is the Miranda warning and when must it be given?", ["right", "silent", "attorney"], 250),
    ("Define tort in legal terms.", ["harm", "civil", "wrong"], 200),
    ("What is the difference between patent and copyright?", ["invention", "original work"], 300),
    ("Explain due process under the 14th Amendment.", ["fair", "law", "rights"], 250),
    ("What is the exclusionary rule?", ["evidence", "illegally", "suppress"], 300),
    ("Explain the concept of sovereign immunity.", ["government", "sued", "consent"], 300),
    ("What is strict liability in tort law?", ["liability", "fault", "defect"], 300),
    ("Define res judicata.", ["final", "judgment", "claim"], 200),
    ("What is the difference between arbitration and mediation?", ["binding", "mediator", "neutral"], 300),
    ("Explain the concept of eminent domain.", ["government", "property", "compensation"], 300),
    ("What is the fruit of the poisonous tree doctrine?", ["evidence", "illegal", "exclude"], 300),
    ("Define the commerce clause of the US Constitution.", ["Congress", "regulate", "commerce"], 300),
    ("What is qualified immunity?", ["government", "official", "protection"], 300),
    ("Explain the difference between express and implied contracts.", ["express", "implied", "terms"], 300),
    ("What is the statute of limitations?", ["time", "file", "claim"], 200),
    ("Define double jeopardy.", ["twice", "same", "offense"], 200),
    ("What is the Daubert standard?", ["expert", "testimony", "scientific"], 300),
    ("Explain the concept of corporate veil piercing.", ["liability", "shareholder", "corporate"], 300),
    ("What are the requirements for standing in federal court?", ["injury", "causation", "redress"], 300),
    ("Define the principle of judicial review.", ["court", "constitution", "law"], 300),
    ("What is promissory estoppel?", ["promise", "reliance", "enforce"], 300),
    ("Explain the difference between misfeasance and malfeasance.", ["wrongful", "improper", "act"], 300),
    ("What is the best evidence rule?", ["original", "document", "copy"], 200),
    ("Define adverse possession.", ["property", "continuous", "years"], 300),
    ("What is the parol evidence rule?", ["written", "contract", "oral"], 300),
    ("Explain the concept of mens rea.", ["intent", "guilty", "mind"], 200),
    ("What is the difference between libel and slander?", ["written", "spoken", "defamation"], 300),
    ("Define the dormant commerce clause.", ["state", "burden", "interstate"], 300),
    ("What are the elements of negligence?", ["duty", "breach", "causation", "damage"], 300),
    ("Explain the concept of specific performance.", ["contract", "court", "compel"], 300),
    ("What is the plain view doctrine?", ["evidence", "officer", "visible"], 200),
    ("Define collateral estoppel.", ["issue", "decided", "preclude"], 300),
    ("What is the difference between a warranty and a guarantee?", ["promise", "defect", "repair"], 300),
    ("Explain the three-part Lemon test.", ["secular", "advance", "entanglement"], 300),
    ("What is forum shopping?", ["court", "favorable", "jurisdiction"], 200),
    ("Define the concept of legal precedent.", ["court", "decision", "binding"], 200),
    ("What is an amicus curiae brief?", ["friend", "court", "interest"], 200),
    ("Explain the rational basis test in constitutional law.", ["legitimate", "government", "interest"], 300),
    ("What is the difference between a bench trial and jury trial?", ["judge", "jury", "decide"], 300),
    ("Define constructive dismissal.", ["resign", "employer", "conditions"], 300),
    ("What is the Chevron deference doctrine?", ["agency", "interpret", "statute"], 300),
    ("Explain the concept of in rem jurisdiction.", ["property", "jurisdiction", "court"], 300),
    ("What are the Federal Rules of Civil Procedure?", ["rules", "federal", "litigation"], 300),
    ("Define the doctrine of unconscionability.", ["unfair", "contract", "one-sided"], 300),
    ("What is the Establishment Clause?", ["religion", "government", "establish"], 300),
    ("Explain the concept of vicarious liability.", ["employer", "employee", "responsible"], 300),
    ("What is the difference between tangible and intangible property?", ["physical", "intellectual", "property"], 300),
    ("Define cy pres doctrine.", ["near", "intent", "charitable"], 300),
    ("What is the rule against perpetuities?", ["interest", "vest", "lives"], 300),
    ("Explain the concept of prosecutorial discretion.", ["prosecutor", "charge", "discretion"], 300),
    ("What is the shopkeeper's privilege?", ["detain", "theft", "retail"], 200),
    ("Define the concept of legal capacity.", ["contract", "age", "mental"], 200),
    ("What is a class action lawsuit and its requirements?", ["class", "common", "numerous"], 300),
    ("Explain the hearsay rule and its exceptions.", ["out-of-court", "statement", "exception"], 300),
]

FINETUNE_TECHNICAL = [
    ("Explain Kubernetes pod scheduling and node affinity.", ["node", "affinity", "schedule"], 400),
    ("Describe how a B-tree index works in a database.", ["tree", "node", "key"], 400),
    ("Explain optimistic vs pessimistic concurrency control.", ["lock", "conflict", "transaction"], 300),
    ("Describe the Raft consensus algorithm.", ["leader", "election", "log"], 400),
    ("Explain how gRPC differs from REST APIs.", ["protocol buffer", "HTTP/2"], 300),
    ("Describe AWS VPC networking including subnets and route tables.", ["subnet", "route", "CIDR"], 400),
    ("Explain the difference between containers and virtual machines.", ["kernel", "hypervisor", "isolation"], 300),
    ("Describe how Prometheus scrapes and stores metrics.", ["scrape", "time series", "target"], 400),
    ("Explain the concept of service mesh and Istio.", ["sidecar", "proxy", "traffic"], 400),
    ("Describe how Terraform manages infrastructure state.", ["state", "plan", "apply"], 300),
    ("Explain Kubernetes RBAC and service accounts.", ["role", "binding", "service account"], 400),
    ("Describe the architecture of Apache Kafka.", ["broker", "partition", "consumer"], 400),
    ("Explain the ELK stack and its components.", ["Elasticsearch", "Logstash", "Kibana"], 400),
    ("Describe how DNS round-robin load balancing works.", ["DNS", "record", "rotate"], 300),
    ("Explain the concept of infrastructure as code.", ["declarative", "version", "reproducible"], 300),
    ("Describe how AWS IAM policies work.", ["policy", "role", "permission"], 400),
    ("Explain the difference between horizontal and vertical scaling.", ["horizontal", "vertical", "scale"], 300),
    ("Describe how a CDN works and its benefits.", ["cache", "edge", "latency"], 300),
    ("Explain Kubernetes ConfigMaps and Secrets.", ["ConfigMap", "Secret", "mount"], 300),
    ("Describe the write-ahead log in database systems.", ["WAL", "log", "recovery"], 300),
    ("Explain the concept of blue-green deployment.", ["blue", "green", "switch"], 300),
    ("Describe how OpenTelemetry works for distributed tracing.", ["trace", "span", "context"], 400),
    ("Explain the purpose of a reverse proxy.", ["proxy", "backend", "client"], 300),
    ("Describe microservices communication patterns.", ["sync", "async", "event"], 400),
    ("Explain the concept of eventual consistency.", ["consistency", "replicate", "partition"], 300),
    ("Describe how Helm charts work in Kubernetes.", ["chart", "values", "template"], 300),
    ("Explain the difference between L4 and L7 load balancing.", ["layer", "TCP", "HTTP"], 300),
    ("Describe the architecture of Redis.", ["memory", "key-value", "persistence"], 300),
    ("Explain Kubernetes StatefulSets vs Deployments.", ["StatefulSet", "persistent", "identity"], 400),
    ("Describe how circuit breaker pattern works.", ["circuit", "open", "fallback"], 300),
    ("Explain the concept of sharding in databases.", ["shard", "partition", "distribute"], 300),
    ("Describe how AWS EKS manages the control plane.", ["EKS", "control plane", "managed"], 300),
    ("Explain the CQRS pattern.", ["command", "query", "separation"], 300),
    ("Describe how TLS mutual authentication works.", ["certificate", "client", "server"], 300),
    ("Explain IPv4 subnetting with CIDR notation.", ["CIDR", "subnet", "mask"], 300),
    ("Describe the saga pattern in microservices.", ["saga", "compensate", "transaction"], 400),
    ("Explain how Grafana dashboards query Prometheus.", ["PromQL", "query", "panel"], 300),
    ("Describe the internals of Docker image layers.", ["layer", "union", "filesystem"], 300),
    ("Explain pod disruption budgets in Kubernetes.", ["PDB", "disruption", "available"], 300),
    ("Describe how AWS S3 achieves durability.", ["S3", "replicate", "region"], 300),
    ("Explain the concept of chaos engineering.", ["chaos", "failure", "resilience"], 300),
    ("Describe how etcd stores Kubernetes cluster state.", ["etcd", "key-value", "raft"], 300),
    ("Explain the difference between NAT and PAT.", ["NAT", "port", "address"], 300),
    ("Describe how Kubernetes HPA works.", ["HPA", "scale", "metric"], 300),
    ("Explain the concept of API gateway pattern.", ["gateway", "route", "auth"], 300),
    ("Describe the architecture of Elasticsearch.", ["index", "shard", "node"], 400),
    ("Explain network policies in Kubernetes.", ["network policy", "ingress", "egress"], 300),
    ("Describe how AWS Lambda cold starts work.", ["cold start", "container", "init"], 300),
    ("Explain the difference between iptables and nftables.", ["iptables", "rule", "chain"], 300),
    ("Describe how Kubernetes operators work.", ["operator", "CRD", "controller"], 400),
    ("Explain the concept of GitOps.", ["Git", "reconcile", "declarative"], 300),
    ("Describe how kernel namespaces enable containers.", ["namespace", "PID", "network"], 300),
    ("Explain the concept of observability vs monitoring.", ["observability", "trace", "metric", "log"], 300),
    ("Describe how AWS Auto Scaling Groups work.", ["ASG", "launch template", "scaling"], 300),
    ("Explain the difference between OLTP and OLAP.", ["transactional", "analytical", "query"], 300),
    ("Describe the architecture of a typical CI/CD pipeline.", ["build", "test", "deploy"], 300),
    ("Explain how Kubernetes admission controllers work.", ["admission", "webhook", "validate"], 400),
    ("Describe the concept of zero-trust networking.", ["trust", "verify", "identity"], 300),
    ("Explain how NATS or NATS JetStream works.", ["NATS", "publish", "subscribe"], 300),
    ("Describe how eBPF enables kernel-level observability.", ["eBPF", "kernel", "probe"], 400),
]

def _finetune_regression(rng):
    """Generate 40 general regression prompts to detect catastrophic forgetting."""
    prompts = []
    # 10 basic math
    for _ in range(10):
        a, b = rng.randint(1, 100), rng.randint(1, 100)
        prompts.append((f"What is {a} + {b}?", [str(a + b)], 50))
    # 10 capitals
    capitals = [
        ("France", "Paris"), ("Germany", "Berlin"), ("Japan", "Tokyo"),
        ("Brazil", "Brasilia"), ("Canada", "Ottawa"), ("Italy", "Rome"),
        ("Spain", "Madrid"), ("India", "New Delhi"), ("China", "Beijing"),
        ("South Korea", "Seoul"),
    ]
    for country, capital in capitals:
        prompts.append((f"What is the capital of {country}?", [capital], 50))
    # 10 science
    science = [
        ("What is the chemical formula for water?", ["H2O"]),
        ("How many planets are in our solar system?", ["8"]),
        ("What is the speed of light approximately?", ["300", "million"]),
        ("What element does O represent?", ["oxygen"]),
        ("What is the freezing point of water in Celsius?", ["0"]),
        ("What gas do humans exhale?", ["CO2", "carbon dioxide"]),
        ("What is the largest mammal?", ["blue whale"]),
        ("How many continents are there?", ["7"]),
        ("What is the center of an atom called?", ["nucleus"]),
        ("What is the chemical symbol for iron?", ["Fe"]),
    ]
    for q, a in science:
        prompts.append((q, a, 50))
    # 10 language
    language = [
        ("What is the past tense of 'go'?", ["went"]),
        ("What is the plural of 'mouse'?", ["mice"]),
        ("What is the opposite of 'hot'?", ["cold"]),
        ("What is a synonym for 'happy'?", ["glad", "joyful", "content"]),
        ("What language is spoken in Brazil?", ["Portuguese"]),
        ("What is the antonym of 'brave'?", ["coward", "timid", "fearful"]),
        ("Spell the word: accommodation.", ["accommodation"]),
        ("What is the comparative form of 'good'?", ["better"]),
        ("What part of speech is 'quickly'?", ["adverb"]),
        ("What is the past participle of 'swim'?", ["swum"]),
    ]
    for q, a in language:
        prompts.append((q, a, 50))
    return prompts

FINETUNE_CROSSDOMAIN = [
    ("A patient with liver cirrhosis needs a contract reviewed. What legal protections exist for patients with chronic illness in employment law?", ["ADA", "disability", "accommodation"], 400),
    ("Explain how HIPAA compliance relates to cloud infrastructure security on AWS.", ["HIPAA", "encryption", "BAA"], 400),
    ("A Kubernetes cluster hosts medical imaging AI. What are the legal liability considerations?", ["liability", "FDA", "device"], 400),
    ("Describe the intersection of tort law and medical malpractice.", ["negligence", "duty", "standard of care"], 400),
    ("How does GDPR affect the architecture of a distributed healthcare system?", ["data", "privacy", "consent"], 400),
    ("Explain the legal implications of AI-generated medical diagnoses.", ["liability", "malpractice", "FDA"], 400),
    ("How do clinical trial regulations affect machine learning model training data?", ["IRB", "consent", "de-identify"], 400),
    ("Describe how container security relates to healthcare data compliance.", ["container", "HIPAA", "encrypt"], 400),
    ("What are the legal requirements for electronic health records?", ["EHR", "meaningful use", "interoperability"], 400),
    ("Explain how observability tools can be configured for HIPAA-compliant logging.", ["PHI", "redact", "audit"], 400),
    ("Describe the intersection of patent law and pharmaceutical development.", ["patent", "drug", "exclusivity"], 400),
    ("How do Kubernetes network policies help achieve PCI-DSS compliance?", ["network policy", "PCI", "segment"], 400),
    ("Explain the legal and technical requirements for digital signatures.", ["PKI", "certificate", "non-repudiation"], 400),
    ("What are the technical and legal considerations for telemedicine platforms?", ["HIPAA", "encryption", "licensing"], 400),
    ("How does the attorney-client privilege apply to electronically stored information?", ["privilege", "ESI", "discovery"], 400),
    ("Describe how infrastructure as code practices relate to SOC 2 compliance.", ["SOC 2", "audit", "control"], 400),
    ("What are the legal implications of using open-source software in medical devices?", ["license", "GPL", "liability"], 400),
    ("How do data retention policies intersect with both HIPAA and legal discovery?", ["retention", "preserve", "destroy"], 400),
    ("Explain the technical and regulatory requirements for medical AI models.", ["FDA", "SaMD", "validation"], 400),
    ("Describe how Kubernetes RBAC maps to healthcare access control requirements.", ["RBAC", "role", "minimum necessary"], 400),
    ("What legal frameworks govern cross-border transfer of medical data?", ["GDPR", "adequacy", "standard clauses"], 400),
    ("How should a cloud architect design for both HIPAA and SOX compliance?", ["encryption", "audit", "separation"], 400),
    ("Explain the legal and technical challenges of medical AI explainability.", ["explainability", "liability", "black box"], 400),
    ("Describe how mTLS in service meshes supports healthcare regulatory requirements.", ["mTLS", "certificate", "HIPAA"], 400),
    ("What are the considerations for deploying LLMs in clinical decision support?", ["FDA", "bias", "validation"], 400),
    ("How do intellectual property laws affect machine learning training data?", ["copyright", "fair use", "data"], 400),
    ("Explain the technical requirements for CJIS compliance in cloud environments.", ["CJIS", "encryption", "background check"], 400),
    ("Describe the intersection of medical ethics and AI bias in healthcare.", ["bias", "fairness", "equity"], 400),
    ("What legal and technical safeguards are needed for genetic data processing?", ["GINA", "genetic", "privacy"], 400),
    ("How do export control regulations affect cloud deployment of AI models?", ["ITAR", "EAR", "export"], 400),
]



# ===================================================================
#  EVAL BENCHMARK  (200 prompts — Judge model scoring calibration)
# ===================================================================

EVAL_COHERENCE = [
    ("Write a structured explanation of how photosynthesis works.", None, 400),
    ("Explain the water cycle with clear transitions between stages.", None, 400),
    ("Describe three causes of the French Revolution in a logical order.", None, 400),
    ("Write a step-by-step guide to setting up a Python virtual environment.", None, 300),
    ("Explain how email works from sender to recipient.", None, 400),
    ("Describe the scientific method in sequential steps.", None, 300),
    ("Write a coherent paragraph explaining why the sky is blue.", None, 300),
    ("Explain the process of making bread from scratch.", None, 300),
    ("Describe how a bill becomes a law in the United States.", None, 400),
    ("Write a structured comparison of electric and gas cars.", None, 400),
    ("Explain the food chain with clear examples at each level.", None, 300),
    ("Describe the lifecycle of a butterfly in order.", None, 300),
    ("Write a logical argument for why exercise is important.", None, 300),
    ("Explain how the internet works in simple terms.", None, 400),
    ("Describe three branches of the US government and their roles.", None, 400),
    ("Write a structured explanation of supply and demand.", None, 400),
    ("Explain how a search engine indexes and retrieves web pages.", None, 400),
    ("Describe the process of human blood circulation.", None, 400),
    ("Write a step-by-step explanation of long division.", None, 300),
    ("Explain how vaccines provide immunity against diseases.", None, 400),
    ("Describe the nitrogen cycle in ecosystems.", None, 400),
    ("Write a coherent explanation of how WiFi works.", None, 300),
    ("Explain the difference between weather and climate.", None, 300),
    ("Describe how a car engine converts fuel to motion.", None, 400),
    ("Write a structured overview of the solar system.", None, 400),
    ("Explain how recycling works from collection to reuse.", None, 300),
    ("Describe the rock cycle with transitions between types.", None, 300),
    ("Write a logical explanation of compound interest.", None, 300),
    ("Explain how sound travels through different media.", None, 300),
    ("Describe the process of evolution by natural selection.", None, 400),
    ("Write a step-by-step guide to making a budget.", None, 300),
    ("Explain how nuclear power plants generate electricity.", None, 400),
    ("Describe the structure of the United Nations.", None, 400),
    ("Write a coherent explanation of how GPS works.", None, 400),
    ("Explain the greenhouse effect and its consequences.", None, 400),
    ("Describe how democracy differs from authoritarianism.", None, 400),
    ("Write a structured explanation of machine learning.", None, 400),
    ("Explain how tides work including the role of the Moon.", None, 300),
    ("Describe the process of protein synthesis in cells.", None, 400),
    ("Write a logical comparison of renewable energy sources.", None, 400),
    ("Explain how a computer boots from power-on to desktop.", None, 400),
    ("Describe the process of photovoltaic energy conversion.", None, 400),
    ("Write a structured overview of the digestive system.", None, 400),
    ("Explain how blockchain technology enables cryptocurrency.", None, 400),
    ("Describe the Krebs cycle in cellular respiration.", None, 400),
    ("Write a coherent explanation of how 3D printing works.", None, 300),
    ("Explain the principles of aerodynamics and flight.", None, 400),
    ("Describe how the human immune system responds to infection.", None, 400),
    ("Write a logical argument for space exploration funding.", None, 400),
    ("Explain how fiber optic cables transmit data.", None, 300),
]

EVAL_HELPFULNESS = [
    ("I want to learn Python. Create a 4-week study plan for beginners.", None, 500),
    ("I need to choose between AWS, GCP, and Azure. Compare them for a startup.", None, 500),
    ("My Docker container keeps crashing. Give me a troubleshooting checklist.", None, 400),
    ("I need to prepare for a system design interview. What should I study?", None, 500),
    ("How do I set up monitoring for a production Kubernetes cluster?", None, 500),
    ("I want to migrate from monolith to microservices. What is the strategy?", None, 500),
    ("My PostgreSQL queries are slow. Give me an optimization checklist.", None, 400),
    ("How do I implement CI/CD for a team of 5 developers?", None, 500),
    ("I need to choose a message queue. Compare Kafka, RabbitMQ, and SQS.", None, 500),
    ("Create a security hardening checklist for a Linux web server.", None, 400),
    ("How do I debug a memory leak in a Node.js application?", None, 400),
    ("I need to design a REST API for an e-commerce platform. Give guidelines.", None, 500),
    ("What are the steps to deploy a machine learning model to production?", None, 500),
    ("I need to set up disaster recovery for an AWS application. How?", None, 500),
    ("Create a checklist for reviewing a pull request.", None, 400),
    ("How do I optimize a React application for performance?", None, 400),
    ("I need to choose between SQL and NoSQL for my project. Help me decide.", None, 500),
    ("What steps should I take to reduce my cloud bill by 30%?", None, 500),
    ("I want to implement feature flags. What are the options and best practices?", None, 500),
    ("How do I handle database migrations in a zero-downtime deployment?", None, 500),
    ("Create a runbook for responding to a production outage.", None, 500),
    ("I need to choose a frontend framework. Compare React, Vue, and Svelte.", None, 500),
    ("How do I implement rate limiting in an API gateway?", None, 400),
    ("I want to set up automated testing. Create a testing strategy.", None, 500),
    ("What are the best practices for managing secrets in Kubernetes?", None, 400),
    ("I need to design a notification system. What architecture should I use?", None, 500),
    ("How do I implement caching effectively in a web application?", None, 400),
    ("Create a checklist for launching a new microservice to production.", None, 500),
    ("I need to implement authentication. Compare JWT, OAuth, and session-based.", None, 500),
    ("How do I troubleshoot network connectivity issues in Kubernetes?", None, 500),
    ("I want to implement infrastructure as code. Where do I start?", None, 500),
    ("What are the steps to secure a REST API?", None, 400),
    ("How do I set up observability for a microservices architecture?", None, 500),
    ("I need to choose a container orchestration tool. Compare K8s, Nomad, ECS.", None, 500),
    ("Create a guide for writing effective technical documentation.", None, 400),
    ("How do I implement a data pipeline for real-time analytics?", None, 500),
    ("I need to scale my database. What are the options?", None, 500),
    ("What are the steps to implement a service mesh?", None, 500),
    ("How do I choose between gRPC and REST for microservices communication?", None, 400),
    ("Create a developer onboarding checklist for a new team member.", None, 400),
    ("I need to implement a search feature. Compare Elasticsearch, Typesense, and Meilisearch.", None, 500),
    ("How do I set up cross-region replication for high availability?", None, 500),
    ("What are the best practices for error handling in distributed systems?", None, 500),
    ("I need to implement a job queue. What are the options?", None, 400),
    ("How do I optimize container images for production?", None, 400),
    ("Create a guide for implementing clean architecture in Python.", None, 500),
    ("I need to implement logging best practices. What should I log and how?", None, 400),
    ("How do I design a multi-tenant SaaS application?", None, 500),
    ("What are the steps to implement blue-green deployments on Kubernetes?", None, 500),
    ("I need to choose a time-series database. Compare Prometheus, InfluxDB, and TimescaleDB.", None, 500),
]

EVAL_FACTUALITY = [
    ("When was the first Moon landing and who commanded the mission?", ["1969", "Armstrong"], 200),
    ("What is the distance from Earth to the Sun in astronomical units?", ["1", "AU"], 100),
    ("Who wrote the Communist Manifesto?", ["Marx", "Engels"], 100),
    ("What is the formula for kinetic energy?", ["1/2", "mv", "v^2"], 150),
    ("What is the population of China approximately?", ["1.4", "billion"], 100),
    ("When was the Berlin Wall built and when did it fall?", ["1961", "1989"], 150),
    ("What is the smallest country in the world by area?", ["Vatican"], 50),
    ("Who discovered the structure of DNA?", ["Watson", "Crick"], 100),
    ("What is the Heisenberg uncertainty principle?", ["position", "momentum", "simultaneously"], 300),
    ("When did the Roman Empire fall?", ["476", "5th"], 100),
    ("What is Planck's constant?", ["6.626", "10^-34"], 100),
    ("Who invented the World Wide Web?", ["Berners-Lee", "Tim"], 100),
    ("What is the mathematical constant e approximately equal to?", ["2.718"], 100),
    ("When was the Magna Carta signed?", ["1215"], 100),
    ("What is the tallest building in the world?", ["Burj Khalifa"], 100),
    ("Who formulated the three laws of motion?", ["Newton"], 100),
    ("What is the chemical formula for sulfuric acid?", ["H2SO4"], 100),
    ("When was the United Nations founded?", ["1945"], 100),
    ("What is the deepest point in the ocean?", ["Mariana", "Challenger"], 100),
    ("Who painted the Sistine Chapel ceiling?", ["Michelangelo"], 100),
    ("What is the speed of sound at sea level?", ["343", "340"], 100),
    ("When was the printing press invented?", ["1440", "1450", "15th"], 100),
    ("What is the Fibonacci sequence?", ["1", "1", "2", "3", "5"], 200),
    ("Who wrote Don Quixote?", ["Cervantes"], 100),
    ("What is the largest lake in Africa?", ["Victoria"], 100),
    ("When was the transistor invented?", ["1947"], 100),
    ("What is the definition of entropy in thermodynamics?", ["disorder", "energy", "heat"], 300),
    ("Who was the first woman to win a Nobel Prize?", ["Curie", "Marie"], 100),
    ("What is the atomic mass of hydrogen?", ["1.008", "1"], 100),
    ("When did the Ottoman Empire end?", ["1922", "1923"], 100),
    ("What is the Doppler effect?", ["frequency", "source", "observer"], 200),
    ("Who proposed the heliocentric model?", ["Copernicus"], 100),
    ("What is the GDP of the United States approximately?", ["25", "trillion"], 100),
    ("When was penicillin discovered?", ["1928"], 100),
    ("What is Euler's identity?", ["e^i", "pi", "+1=0", "=-1"], 150),
    ("Who was the last pharaoh of Egypt?", ["Cleopatra"], 100),
    ("What is the melting point of iron in Celsius?", ["1538", "1535"], 100),
    ("When was the Suez Canal opened?", ["1869"], 100),
    ("What is the universal gas constant R?", ["8.314"], 100),
    ("Who invented the telephone?", ["Bell"], 100),
    ("What is the surface area of Earth in square kilometers?", ["510", "million"], 100),
    ("When was the first successful heart transplant?", ["1967"], 100),
    ("What is the charge of a proton in coulombs?", ["1.6", "10^-19"], 100),
    ("Who wrote The Origin of Species?", ["Darwin"], 100),
    ("What is the orbital period of Earth around the Sun?", ["365", "days"], 100),
    ("When was the Internet protocol suite (TCP/IP) standardized?", ["1983"], 100),
    ("What is the density of water at 4 degrees Celsius?", ["1000", "1 g"], 100),
    ("Who developed the periodic table?", ["Mendeleev"], 100),
    ("What is the Chandrasekhar limit?", ["1.4", "solar mass"], 150),
    ("When was the Hubble Space Telescope launched?", ["1990"], 100),
]

EVAL_EDGECASE = [
    ("Is a hot dog a sandwich? Give a reasoned argument.", None, 400),
    ("Explain why the number 0 is even.", None, 300),
    ("Is Pluto a planet? Explain the scientific debate.", None, 400),
    ("Can you prove that 1+1=2?", None, 500),
    ("Write a paradox and explain why it is paradoxical.", None, 400),
    ("Is mathematics discovered or invented? Argue both sides.", None, 500),
    ("Explain the Ship of Theseus problem.", None, 400),
    ("Is it possible to think about nothing? Explain.", None, 300),
    ("Are there more grains of sand on Earth or stars in the universe?", None, 400),
    ("Can an AI be creative? Argue for and against.", None, 500),
    ("Explain the trolley problem and why it has no clear answer.", None, 400),
    ("Is infinity a number? Explain.", None, 300),
    ("Can you hear silence? Discuss.", None, 300),
    ("Is zero positive, negative, or neither?", ["neither"], 200),
    ("What happens when an unstoppable force meets an immovable object?", None, 400),
    ("Is the glass half full or half empty? Give an engineer's answer.", None, 300),
    ("Explain the grandfather paradox in time travel.", None, 400),
    ("Is it ethical to eat meat? Present both perspectives.", None, 500),
    ("Can a machine understand language or only simulate understanding?", None, 500),
    ("What color is a mirror?", None, 300),
    ("If you replace every part of a car, is it still the same car?", None, 400),
    ("Is there a difference between being alive and not being dead?", None, 300),
    ("Explain why we park in driveways and drive on parkways.", None, 300),
    ("Can something be both true and false at the same time?", None, 400),
    ("Is math the language of the universe or a human construct?", None, 500),
    ("What would happen if everyone on Earth jumped at the same time?", None, 400),
    ("Is the color you see as blue the same blue I see?", None, 400),
    ("Can you step in the same river twice?", None, 300),
    ("Is a person who has lost all their memories still the same person?", None, 400),
    ("Explain why a set of all sets cannot contain itself.", None, 400),
    ("What came first, the chicken or the egg? Give a scientific answer.", None, 400),
    ("Is free will compatible with a deterministic universe?", None, 500),
    ("Can you define consciousness? Why is it hard to define?", None, 500),
    ("Is it possible to have a language with only one word?", None, 300),
    ("Explain the Banach-Tarski paradox in simple terms.", None, 400),
    ("Can we know what we do not know?", None, 300),
    ("Is the absence of evidence evidence of absence?", None, 400),
    ("What is the sound of one hand clapping?", None, 300),
    ("Can a liar truthfully say they are lying?", None, 300),
    ("Is a copy of a masterpiece art?", None, 400),
    ("Explain the Fermi paradox.", None, 400),
    ("Is time travel theoretically possible? What does physics say?", None, 500),
    ("Can an infinite hotel always accommodate one more guest?", None, 400),
    ("What would the world look like if pi were exactly 3?", None, 500),
    ("Is there a largest prime number?", ["no", "infinitely"], 200),
    ("Can you have a thought without language?", None, 400),
    ("Is simplicity always better in design?", None, 400),
    ("Explain the coastline paradox.", None, 400),
    ("Is there a meaningful difference between 0.999... and 1?", ["equal", "same", "no"], 300),
    ("Can artificial intelligence have emotions?", None, 500),
]


# ===================================================================
#  MAIN — Generate all benchmark promptsets
# ===================================================================

def main():
    parser = argparse.ArgumentParser(description="Generate benchmark promptsets")
    parser.add_argument("--output-dir", default="data/promptsets",
                        help="Output directory (default: data/promptsets)")
    args = parser.parse_args()

    output_base = Path(args.output_dir)
    gen = PromptsetGenerator(seed=42)
    rng = random.Random(42)

    # ---- Quant benchmark (250 prompts) ----
    quant_prompts = []
    quant_prompts += expand(_quant_math(rng), "bq-m", "math_precision", "math", 100)
    quant_prompts += expand(QUANT_REASONING, "bq-r", "reasoning", "reasoning")
    quant_prompts += expand(QUANT_CODE, "bq-c", "code_gen", "code")
    quant_prompts += expand(QUANT_FACTUAL, "bq-f", "factual_recall", "factual")
    quant_prompts += expand(QUANT_LONGFORM, "bq-l", "long_form", "long_form")

    quant_dir = output_base / "benchmark-quant"
    quant_dir.mkdir(parents=True, exist_ok=True)
    qm = gen.generate_promptset(
        scenario_id="benchmark-quant-v1",
        dataset_id="benchmark-quant",
        prompts=[{**p, "target_output_tokens": p.get("max_tokens", 200)} for p in quant_prompts],
        output_dir=quant_dir,
    )
    print(f"[benchmark-quant]    {qm.prompt_count} prompts -> {quant_dir}")

    # ---- Finetune benchmark (250 prompts) ----
    ft_prompts = []
    ft_prompts += expand(FINETUNE_MEDICAL, "bf-med", "medical", "medical")
    ft_prompts += expand(FINETUNE_LEGAL, "bf-leg", "legal", "legal")
    ft_prompts += expand(FINETUNE_TECHNICAL, "bf-tech", "technical", "technical")
    ft_prompts += expand(_finetune_regression(rng), "bf-reg", "regression", "regression", 50)
    ft_prompts += expand(FINETUNE_CROSSDOMAIN, "bf-xd", "cross_domain", "cross_domain")

    ft_dir = output_base / "benchmark-finetune"
    ft_dir.mkdir(parents=True, exist_ok=True)
    fm = gen.generate_promptset(
        scenario_id="benchmark-finetune-v1",
        dataset_id="benchmark-finetune",
        prompts=[{**p, "target_output_tokens": p.get("max_tokens", 200)} for p in ft_prompts],
        output_dir=ft_dir,
    )
    print(f"[benchmark-finetune] {fm.prompt_count} prompts -> {ft_dir}")

    # ---- Eval benchmark (200 prompts) ----
    eval_prompts = []
    eval_prompts += expand(EVAL_COHERENCE, "be-coh", "coherence", "coherence")
    eval_prompts += expand(EVAL_HELPFULNESS, "be-help", "helpfulness", "helpfulness")
    eval_prompts += expand(EVAL_FACTUALITY, "be-fact", "factuality", "factuality")
    eval_prompts += expand(EVAL_EDGECASE, "be-edge", "edge_case", "edge_case")

    eval_dir = output_base / "benchmark-eval"
    eval_dir.mkdir(parents=True, exist_ok=True)
    em = gen.generate_promptset(
        scenario_id="benchmark-eval-v1",
        dataset_id="benchmark-eval",
        prompts=[{**p, "target_output_tokens": p.get("max_tokens", 200)} for p in eval_prompts],
        output_dir=eval_dir,
    )
    print(f"[benchmark-eval]     {em.prompt_count} prompts -> {eval_dir}")

    total = qm.prompt_count + fm.prompt_count + em.prompt_count
    print(f"\nBenchmark total: {total} prompts across 3 promptsets")
    print(f"\nUse the Test Harness 'Run Benchmark' button in Grafana to execute.")


if __name__ == "__main__":
    main()

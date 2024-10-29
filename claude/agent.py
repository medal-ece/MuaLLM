import os
from dotenv import load_dotenv
from openai import OpenAI
import re
import argparse
from messages import system_message
import datetime

# Load environment variables from .env file
load_dotenv()

# Access the API key from environment variables
api_key = os.getenv('CLAUDE_API_KEY')
        
# Initialize the OpenAI client with the API key
client = OpenAI(api_key=api_key)

# Dummy functions for circuit analysis tools
def analyze_circuit_details(circuit_id: str) -> str:
    """Dummy function to analyze circuit details"""
    dummy_analysis = {
        "bgr_001": """Circuit Analysis for BGR_001:
- Architecture: Standard bandgap reference
- Core components: 
  * 6 MOSFETs
  * 3 resistors
  * 1 capacitor
- Performance:
  * Supply voltage: 1.2V
  * Power consumption: 100nW
  * Temperature range: -40°C to 85°C""",
        "bgr_002": """Circuit Analysis for BGR_002:
- Architecture: Sub-bandgap reference
- Core components: 
  * 4 MOSFETs in subthreshold region
  * 2 resistors for voltage division
  * No capacitors needed
- Performance:
  * Supply voltage: 0.7V
  * Power consumption: 52.5nW
  * Temperature range: -20°C to 80°C""",
        "bgr_003": """Circuit Analysis for BGR_003:
- Architecture: Traditional bandgap
- Core components:
  * 8 MOSFETs
  * 4 resistors
  * 2 capacitors
- Performance:
  * Supply voltage: 1.8V
  * Power consumption: 200nW
  * Temperature range: -55°C to 125°C"""
    }
    return dummy_analysis.get(circuit_id.lower(), "Circuit not found in database")

def get_circuit_netlist(circuit_id: str) -> str:
    """Dummy function to return circuit netlist"""
    dummy_netlists = {
        "bgr_001": """M1 VDD BIAS1 NODE1 VDD PMOS W=2u L=0.5u
M2 NODE1 BIAS1 GND GND NMOS W=1u L=0.5u
M3 VDD BIAS2 VREF GND NMOS W=1u L=0.5u
R1 NODE1 VREF 200k
C1 VREF GND 1p
VDD VDD GND DC 1.2V""",
        "bgr_002": """M1 VDD GATE1 NODE1 VDD PMOS W=2u L=0.5u
M2 NODE1 GATE1 GND GND NMOS W=1u L=0.5u
M3 VDD GATE2 VREF GND NMOS W=1u L=0.5u
M4 VREF GATE2 GND GND NMOS W=1u L=0.5u
R1 NODE1 VREF 100k
R2 VREF GND 50k
VDD VDD GND DC 0.7V""",
        "bgr_003": """M1 VDD BIAS1 NODE1 VDD PMOS W=4u L=0.5u
M2 NODE1 BIAS1 NODE2 GND NMOS W=2u L=0.5u
M3 NODE2 BIAS2 VREF GND NMOS W=2u L=0.5u
R1 NODE1 NODE2 300k
C1 NODE2 GND 2p
VDD VDD GND DC 1.8V"""
    }
    return dummy_netlists.get(circuit_id.lower(), "Netlist not found in database")

def compare_circuit_designs(circuit_ids: list) -> str:
    """Dummy function to compare multiple circuit designs"""
    comparison_table = """Comparison Table:
| Parameter          | BGR_001 | BGR_002 | BGR_003 |
|-------------------|---------|---------|---------|
| Supply Voltage    | 1.2V    | 0.7V    | 1.8V    |
| Power             | 100nW   | 52.5nW  | 200nW   |
| Temp. Coeff.      | 10ppm/°C| 15ppm/°C| 8ppm/°C |
| Reference Voltage | 1.09V   | 0.55V   | 1.2V    |
| Process Variation | ±1.5%   | ±2%     | ±1%     |
| Area              | 0.015mm²| 0.012mm²| 0.018mm²|"""
    return comparison_table

def dummy_search(query: str) -> str:
    return """Found 3 relevant designs:
1. BGR_001: 1.2V supply, 100nW power consumption
2. BGR_002: 0.7V supply, 52.5nW power consumption
3. BGR_003: 1.8V supply, 200nW power consumption"""

class CircuitAgent:
    def __init__(self):
        self.system_message = system_message
        self.messages = [{"role": "system", "content": self.system_message}]
        
    def __call__(self, query):
        self.messages.append({"role": "user", "content": query})
        result = self.execute()
        self.messages.append({"role": "assistant", "content": result})
        return result

    def execute(self):
        completion = client.chat.completions.create(
            model="gpt-4",  # Changed to GPT-4 since we're using OpenAI
            temperature=0,
            messages=self.messages
        )
        return completion.choices[0].message.content

# Available actions from the system message
known_actions = {
    "search_database": dummy_search,
    "analyze_circuit": analyze_circuit_details,
    "get_netlist": get_circuit_netlist,
    "compare_designs": compare_circuit_designs
}

# Regular expression to match actions
action_re = re.compile(r'^Action: (\w+): (.*)$')

def write_to_log(content: str, filename: str = "circuit_analysis_log.txt", mode: str = "a"):
    """Write content to log file with timestamp"""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(filename, "a") as f:
        f.write(f"\n[{timestamp}]\n{content}\n{'-'*50}\n")

def query_circuit(question, max_turns=10):
    i = 0
    agent = CircuitAgent()
    next_prompt = question
    write_to_log(f"Query: {question}", "circuit_analysis_log.txt", "w")  # Start new log
    
    while i < max_turns:
        i += 1
        result = agent(next_prompt)
        print(result)
        write_to_log(f"Assistant Response:\n{result}")
        
        actions = [
            action_re.match(a) 
            for a in result.split('\n') 
            if action_re.match(a)
        ]
        
        if actions:
            action, action_input = actions[0].groups()
            
            if action not in known_actions:
                error_msg = f"Unknown action: {action}: {action_input}"
                write_to_log(f"Error: {error_msg}")
                raise Exception(error_msg)
                
            print(f"Running {action}: {action_input}")
            write_to_log(f"Action: {action}\nInput: {action_input}")
            
            if action == "compare_designs":
                # Handle list input for compare_designs
                try:
                    circuit_ids = action_input.strip('[]').replace(' ', '').split(',')
                    observation = known_actions[action](circuit_ids)
                except Exception as e:
                    error_msg = f"Invalid circuit IDs format: {action_input}. Error: {str(e)}"
                    write_to_log(f"Error: {error_msg}")
                    raise Exception(error_msg)
            else:
                observation = known_actions[action](action_input)
                
            write_to_log(f"Observation:\n{observation}")
            next_prompt = f"Observation: {observation}"
        else:
            # Write final summary to a separate file
            write_final_summary(question, result)
            return

def write_final_summary(query: str, final_response: str):
    """Write the final analysis summary to a separate file"""
    with open("circuit_analysis_summary.txt", "w") as f:
        f.write("Circuit Analysis Summary\n")
        f.write("=" * 50 + "\n\n")
        f.write(f"Query: {query}\n\n")
        f.write("Final Recommendation:\n")
        f.write("-" * 20 + "\n")
        f.write(final_response + "\n")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", type=str, required=True, help="Query about circuit design")
    args = parser.parse_args()
    
    query_circuit(args.query)

if __name__ == "__main__":
    main()

from pydantic import BaseModel
from openai import OpenAI
import base64
import os
import json
from dotenv import load_dotenv

load_dotenv()

client = OpenAI()

class TableData(BaseModel):
    table_data: list[list[str]]
image_path = "claude/agent_db/images/image_14.jpg"
base64_image = base64.b64encode(open(image_path, "rb").read()).decode("utf-8")

completion = client.beta.chat.completions.parse(
    model="gpt-4o-2024-08-06",
    messages=[
        {"role": "system", "content": "Extract the table information."},
        {"role": "user", "content": f"Here is the image: {base64_image}"},
    ],
    response_format=TableData,
)

table_data = completion.choices[0].message.parsed

print(table_data)
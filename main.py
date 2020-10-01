from slack import WebClient
from slackeventsapi import SlackEventAdapter
from flask import Flask

import os
import logging
import gradescope
import random
import math

COURSE_ID = '180986'

app = Flask(__name__)
slack_events_adapter = SlackEventAdapter(os.environ.get("SLACK_EVENTS_TOKEN"), "/slack/events", app)
slack_web_client = WebClient(token=os.environ.get("SLACK_TOKEN"))

done_texts = set()

def get_most_recent_hw():
    assignments = gradescope.get_course_assignments(COURSE_ID)
    return max(assignments, key=lambda x: 0 if 'Homework' not in x['name'] else int(x['name'].split(' ')[-1]))

def get_num_submissions(hw_id):
    grades = gradescope.get_assignment_grades(COURSE_ID, hw_id)
    return sum(1 if student['Status'] != 'Missing' else 0 for student in grades)

def get_allocations(total, num_splits):
    split_len = math.ceil(total / num_splits)
    return [(i*split_len + 1, min(total, (i+1)*split_len)) for i in range(num_splits)]

def assemble_question_info(question, total):
    graders = question['graders']
    random.shuffle(graders)
    return f"{question['name']}: {', '.join(f'{grader} ({qs[0]}-{qs[1]})' for grader, qs in zip(graders, get_allocations(total, len(graders))))}"

@slack_events_adapter.on("message")
def message(payload):
    event = payload.get("event", {})

    if 'text' not in event:
        return

    message = event['text']

    if message in done_texts:
        return

    done_texts.add(message)

    channel = event['channel']

    message_lines = message.split('\n')

    if len(message_lines) < 2:
        return

    if 'allocation' not in message_lines[0].lower():
        return

    allocation_lines = [i+1 for i, line in enumerate(message_lines[1:]) if ':' in line]

    curr_hw = get_most_recent_hw()
    num_submissions = get_num_submissions(curr_hw['id'])
    hw_name = curr_hw['name']

    questions = []
    for line in allocation_lines:
        txt = message_lines[line].split(':')
        if len(txt) != 2:
            continue
        questions.append({
            'name': txt[0],
            'graders': [i.strip() for i in txt[1].split(',')]
        })

    return_msg = f"Grader splits for {hw_name}:\n"
    return_msg += '\n'.join(assemble_question_info(q, num_submissions) for q in questions)

    print(f"Calculated grader splits for {hw_name}")
    slack_web_client.chat_postMessage(channel=channel, text=return_msg)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3002)

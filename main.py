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

def get_named_assignment(name):
    assignments = gradescope.get_course_assignments(COURSE_ID)
    return [i for i in assignments if i['name'] == name][0]

def get_num_submissions(hw_id):
    grades = gradescope.get_assignment_grades(COURSE_ID, hw_id)
    return sum(1 if student['Status'] != 'Missing' else 0 for student in grades)

def get_allocations(total, graders):
    grader_map = {}
    need_grader = []
    total_already_assn = 0

    for grader in graders:
        if '(' in grader:
            try:
                total_already_assn += int(grader[grader.index('(')+1:grader.index(')')])
                grader_map[grader.split('(')[0].strip()] = int(grader[grader.index('(')+1:grader.index(')')])
            except:
                need_grader.append(grader)
        else:
            need_grader.append(grader)

    if total_already_assn > total:
        return "Too many preassigned graders!"

    split_len = math.ceil((total - total_already_assn) / len(need_grader))
    random.shuffle(need_grader)
    for grader in need_grader[:-1]:
        grader_map[grader] = split_len

    grader_map[need_grader[-1]] = total - total_already_assn - (len(need_grader) - 1) * split_len

    gs = list(grader_map.keys())
    curr = 0
    random.shuffle(gs)
    ans = []

    for g in gs:
        ans.append(f"{g} ({curr+1}-{curr+grader_map[g]})")
        curr += grader_map[g]

    return ', '.join(ans)

def assemble_question_info(question, total):
    graders = question['graders']
    # random.shuffle(graders)
    # return f"{question['name']}: {', '.join(f'{grader} ({qs[0]}-{qs[1]})' for grader, qs in zip(graders, get_allocations(total, len(graders))))}"
    return f"{question['name']}: {get_allocations(total, graders)}"

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

    curr_hw = get_most_recent_hw() if '[' not in message_lines[0] else get_named_assignment(message_lines[0][message_lines[0].index('[')+1:message_lines[0].index(']')])
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

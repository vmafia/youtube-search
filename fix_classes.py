import os

file_path = r'frontend/src/App.tsx'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace('className="grid3"', 'className="dashboard-grid"')
content = content.replace('className="card card stat-card"', 'className="card stat-card"')
content = content.replace('className="card card card"', 'className="card stat-card"')
content = content.replace('card card stat-card', 'card stat-card')
content = content.replace('card card video-card-checkbox-wrapper', 'video-card-checkbox-wrapper')
content = content.replace('card card video-card-thumbnail', 'video-card-thumbnail')
content = content.replace('card card video-card-info', 'video-card-info')
content = content.replace('card card video-card-title', 'video-card-title')
content = content.replace('card card video-card-date', 'video-card-date')
content = content.replace('card card dashboard-list-card', 'card dashboard-list-card')

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

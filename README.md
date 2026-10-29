# Взломай умный город

## Локальный запуск (без Redis)
```
pip install flask redis gunicorn
redis-server &
python server.py
```

## Деплой на Render
1. Залить папку в GitHub-репозиторий.
2. На render.com → New → Blueprint → выбрать репозиторий. Render прочитает render.yaml
   и сам создаст сервис приложения и Redis (Key Value), свяжет их переменной REDIS_URL
   и сгенерирует ADMIN_KEY автоматически.
3. После деплоя откройте вкладку Environment сервиса smartcity, посмотрите значение
   ADMIN_KEY — это ваш ключ для /admin.
4. Бесплатный план Render засыпает после 15 минут без запросов. Минут за 5-10
   до начала пары откройте главную страницу сами, чтобы сервис "проснулся".

## Управление игрой
- Игроки: https://ваш-домен.onrender.com
- Проектор: https://ваш-домен.onrender.com/board
- Админка: https://ваш-домен.onrender.com/admin?key=ВАШ_КЛЮЧ

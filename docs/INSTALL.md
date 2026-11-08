# Установка на Raspberry Pi

## Подготовка образа

В Raspberry Pi Imager включите SSH, задайте пользователя и hostname. Для текущего
стенда это `pomehi` и `pomehi.local`. Секреты не храните в репозитории.
Камера подключается к CAMERA/CSI при выключенном питании. Убедитесь, что
`rpicam-hello --list-cameras` показывает IMX219.

64-битная Raspberry Pi OS предпочтительна для Pi4. Проверьте:

```bash
uname -m
cat /etc/os-release
```

## Получить код без настройки GitHub на Pi

Вариант с ноутбука, из локального checkout `bvs-camera`:

```bash
tar --exclude=.git --exclude=keys --exclude='*.key' --exclude=vendor \
  --exclude=results --exclude=__pycache__ --exclude=build --exclude='*.egg-info' \
  -czf - . | ssh pomehi@pomehi.local 'mkdir -p ~/bvs-camera; tar -xzf - -C ~/bvs-camera'
ssh pomehi@pomehi.local
cd ~/bvs-camera
bash scripts/install-pi.sh
```

Ключи передаются отдельно по защищённому каналу. Скрипт установки собирает
зафиксированный WFB commit `a5e7205d0b8608d15a06cdac2ac4e444544f8624`.
Интерфейсы сети и firmware-config этим скриптом не меняются.

Для рабочего образа со старой папкой `~/skvoz-video` передача исходников не
заменяет уже работающий процесс. Сначала остановите прежний передатчик,
освободите камеру и порты, затем запускайте новый. Старые файлы автоматически
не удаляются.

## Отдельная проверка камеры и контроллера

```bash
bash scripts/run-module.sh adaptive_server --mode camera-only --manual
```

Это захват и выдача RTP на локальный порт 5600 без WFB. НСУ сама по себе такой
локальный UDP не увидит: нужен отдельный транспорт или локальный тестовый приёмник.
`--manual` нужен, чтобы отсутствие обратной связи не переключало профиль теста.
Статус — `curl http://127.0.0.1:8090/status`. Перед основным запуском завершите
этот тест через Ctrl+C.

## Запуск как служба

Сначала проверьте ручной radio-запуск по README, ключи и имя интерфейса.
Шаблон рассчитан на `/home/pomehi/bvs-camera`, внешний `wlan1`, запуск root.
Для другого пользователя/пути исправьте WorkingDirectory и ExecStart.

```bash
sudo install -m 644 systemd/bvs-camera.service /etc/systemd/system/bvs-camera.service
sudo systemctl daemon-reload
sudo systemctl start bvs-camera
sudo systemctl status bvs-camera --no-pager
journalctl -u bvs-camera -n 50 --no-pager
```

Включение при загрузке — отдельное действие, после успешного ручного теста:

```bash
sudo systemctl enable bvs-camera
```

Остановка/перезапуск:

```bash
sudo systemctl stop bvs-camera
sudo systemctl restart bvs-camera
```

Не запускайте одновременно службу и второй экземпляр из терминала. Служба
сама по себе не настраивает NetworkManager и не устанавливает драйвер:
это предварительные условия из RADIO.md.

IP-режим можно запускать из терминала без root. При необходимости собственной
службы замените ExecStart на команду `start-air.sh --mode ip --bind ... --peer ...`
и выберите пользователя с доступом к камере.

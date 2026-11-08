# Внешний Wi-Fi и прямой WFB

Прямой WFB требует monitor/injection и совместимого драйвера на обеих сторонах.
Обычное подключение адаптера к SSID или наличие устройства в Windows ещё не
означает готовность WFB.

Для RTL8812AU используется [patched svpcom/rtl8812au](https://github.com/svpcom/rtl8812au),
ветка v5.2.20, зафиксированный commit `3577999972f350a2213e7509ae1f371b99fc96ab`.
Рекомендации проекта: [WFB-ng Setup HOWTO](https://github.com/svpcom/wfb-ng/wiki/Setup-HOWTO).

## Драйвер Pi

Проверьте заголовки именно работающего ядра:

```bash
uname -r
ls /lib/modules/$(uname -r)/build/Makefile
```

Если их нет, установите соответствующие заголовки из репозиториев Raspberry Pi
OS. Заголовки другой версии не заменяют нужные; после обновления ядра может
потребоваться перезагрузка и новая сборка. Скрипт сам не обновляет ядро.

```bash
bash scripts/install-radio-driver.sh
```

Он собирает и устанавливает `88XXau_wfb.ko`, но не выгружает текущий драйвер
и не переключает адаптер. После проверки отдельного доступа по Ethernet
активация выглядит так (имена — примеры):

```bash
# SSH должен идти через Ethernet/другой интерфейс, а не wlan1.
sudo nmcli device set wlan1 managed no
sudo ip link set wlan1 down
sudo modprobe -r rtw88_8812au
sudo modprobe 88XXau_wfb rtw_power_mgnt=0 rtw_enusbss=0
```

Если текущий драйвер называется иначе, не выгружайте модули наугад. Определите
его через `readlink -f /sys/class/net/wlan1/device/driver` и документацию своей
сборки. Для сохранения unmanaged-состояния при переобнаружении используйте
отдельную конфигурацию NetworkManager, привязанную к MAC именно внешнего радио.
Не отключайте NetworkManager целиком.

Проверьте после переобнаружения:

```bash
ip -brief address
readlink -f /sys/class/net/wlan1/device/driver
iw dev
```

Глобального IP на выделенном WFB-интерфейсе быть не должно. Если он автоматически
подключился к SSID, сначала отключите этот профиль на выбранном адаптере и снова
выставьте unmanaged. Launcher откажется менять интерфейс с глобальным IP.
Встроенный wlan0 защищён; USB-интерфейс с таким именем допустим только после
остальных проверок. Мощность принудительно не повышается.

## Запуск

Сверьте `config/link.json` с `nsy-server/config/station.json`: link_id, частота,
полоса и ключевая пара. По умолчанию — link 1, 2412 МГц, HT20.

```bash
sudo bash start-air.sh --mode radio --interface wlan1
```

При остановке восстанавливается прежний тип интерфейса, но не прежний SSID
и не политика NetworkManager. Чтобы вернуть адаптер в обычную сеть, явно
включите managed в NetworkManager и активируйте свой сохранённый профиль.

Никакие приведённые команды не являются измерением дальности или задержки.

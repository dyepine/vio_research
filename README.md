# VIO research: preparation of selected public recordings

Общее описание задачи, текущего состояния и целевого результата: **[OVERVIEW.md](OVERVIEW.md)**. Дальнейшие действия: **[PLAN.md](PLAN.md)**.

Этот README описывает первоначальный загрузчик/экспортер. Текущий эксперимент на GrandTour Alphasense использует VSLAM-LAB — это отдельный путь подготовки и запуска.

Минимальная подготовка данных без ROS-установки. Makefile управляет окружением и стадиями; Python отвечает за загрузку, проверку и конвертацию.

## Клонирование

```bash
git clone --recurse-submodules https://github.com/dyepine/vio_research.git
cd vio_research
make test
```

VSLAM-LAB подключён как submodule с зафиксированной ревизией. Если репозиторий уже клонирован без submodules: `git submodule update --init --recursive`. Датасеты, результаты, окружения и кеш не публикуются.

Для настроек конкретной машины можно создать `configs/datasets/prepare.local.yaml` и `configs/experiments/grandtour_alb2_orbslam3.local.yaml` — они игнорируются Git и автоматически выбираются вместо основных YAML. В локальном эксперименте укажите `StorageConfig: configs/datasets/prepare.local.yaml`, если используете локальные пути данных. Клонирование само по себе не устанавливает Pixi и окружения VSLAM-LAB.

## Запуск ORB-SLAM3 через VSLAM-LAB

Из корня проекта: `make run`. Makefile настраивает локальный Pixi, кеш и число потоков; ручные `export` и переход в каталог VSLAM-LAB не нужны. Требуются уже установленные `.tools/pixi` и окружения VSLAM-LAB.

Настройки эксперимента и `ResultsDir` задаются в `configs/experiments/grandtour_alb2_orbslam3.yaml`, путь данных — в `configs/datasets/prepare.yaml`. Перед новой попыткой укажите новый, ещё не существующий `ResultsDir`: адаптер отказывается перезаписывать результаты. Проверки камер/IMU выполняются автоматически; вывод идёт в терминал, native log и отчёты сохраняются в `ResultsDir`.

`scripts/run_grandtour_alb2.py` — внешняя обвязка существующих API VSLAM-LAB, не альтернативная реализация алгоритма. Она задаёт пути на отдельных объектах датасета/эксперимента, не меняя файлы фреймворка или его глобальные константы. Входы остаются в формате VSLAM-LAB: `rgb.csv`, `imu_0.csv`, `calibration.yaml` и каталоги изображений. Подготовку экспериментальных CSV/калибровки, команду запуска и защиту RAM выполняет VSLAM-LAB. Проверка окна камер/IMU вынесена в `scripts/check_vio_inputs.py`. Эталон GNSS/INS не читается при запуске и должен проверяться отдельно перед оценкой; автоматическая оценка с коррекцией масштаба не вызывается.

**До устранения отключений T7 и проверки целостности данных новый прогон не запускать.** Подробнее о текущем состоянии — в `PLAN.md`.

## Быстрый старт

Python >= 3.10, `make`, модуль `venv`, доступ в интернет для первоначальной установки зависимостей и загрузки файлов.

Конфиги находятся в `configs/`, настройки датасетов — в `configs/datasets/`:

```text
configs/
  datasets/
    prepare.yaml   # папка данных, активные записи, лимиты места
    datasets.json  # официальные URL, размеры, checksums и revisions
```

Настройки находятся в **`configs/datasets/prepare.yaml`**. Отредактируй папку и активные последовательности:

```yaml
data_dir: ~/datasets/vio_research
max_data_gb: 125
reserve_gb: 15
sequences:
  grandtour-alb2: true
  grandtour-trim1: false
  botanicgarden-1018-00: false
  botanicgarden-1005-00: false
```

`true` — обрабатывать, `false` — пропустить. По умолчанию активна только ALB-2; остальные включай после проверки первой записи. Порядок строк задаёт порядок обработки. Выключение записи **не удаляет** уже скачанные данные. Для всех четырёх поставь все значения в `true`; прежде проверь место.

```bash
cd ~/coding/vio_research
make plan       # выбранные в YAML записи; без загрузки датасетов
make prepare    # загрузка, конвертация и проверка тех же записей
make download   # только загрузка
make convert    # только конвертация
make validate   # повторная структурная проверка
make test       # offline synthetic tests
```

Первый запуск может установить Python-пакеты. `~` в `data_dir` раскрывается как HOME, относительный путь считается от папки YAML, не от текущей рабочей директории. Неизвестные имена, повторные ключи YAML, значения вроде строки `"false"`, некорректные лимиты и пустой активный набор вызывают ошибку до загрузки.

**YAML — единственный источник параметров данных.** Папка, последовательности и лимиты читаются только из него, без переопределений через make, окружение или Python CLI. Старые make-параметры `DATA_DIR`, `SEQUENCES`, `MAX_DATA_GB`, `RESERVE_GB` и соответствующие CLI-флаги больше не поддерживаются.

Можно выбрать другой YAML, не меняя механизм настройки:

```bash
make plan CONFIG=/path/to/another.yaml
```

`configs/datasets/datasets.json` остаётся каталогом официальных URL/checksums; для выбора записей его редактировать не нужно.

Повторный `prepare` использует проверенные исходники и не перезаписывает готовые результаты. Версия конвертера или manifest изменилась? Старый результат нужно явно переместить в другую папку. Сбой конвертации удаляет только её временный каталог; исходники и частичные загрузки сохраняются. При `convert` все исходные файлы должны присутствовать.

## Место на диске

Доступны для выбора в `configs/datasets/prepare.yaml`:

| Идентификатор | Запись | Объём исходников | Консервативная оценка результата |
|---|---|---:|---:|
| `grandtour-alb2` | `2024-11-15-11-37-15` | 5.01 GB | 34.03 GB |
| `grandtour-trim1` | `2024-11-15-10-16-35` | 5.35 GB | 31.23 GB |
| `botanicgarden-1018-00` | `1018_00_VLIO.bag` | 5.83 GB | 1.91 GB |
| `botanicgarden-1005-00` | `1005_00_VLIO.bag` | 32.32 GB | 7.38 GB |

Размер PNG заранее неизвестен. Оценка использует несжатые grayscale pixels + запас; обычно фактический размер меньше. Если включить все четыре записи, все исходники + результат оцениваются в **123.1 decimal GB**, ещё **15 GB** оставляются свободными. Для одной активной ALB-2 оценка данных — **39.04 GB** плюс резерв. Учитываются уже находящиеся в папке `data_dir` файлы и реальное свободное место выбранной файловой системы. Ограничения задаются только полями `max_data_gb` и `reserve_gb` в YAML. После их изменения запусти `make plan`.

Конвертация идёт последовательно. GrandTour image tar читается напрямую: не создаётся дополнительная полная папка исходных JPEG. LiDAR, depth, дополнительные камеры, карты и splats не скачиваются. BotanicGarden опубликован монолитным VLIO bag: при загрузке приходится получить весь bag, но экспортируются только gray stereo, Xsens и corrected reference.

Исходники автоматически **не удаляются**. Данные вне папки `data_dir`, окружение и системные файлы не входят в лимит `max_data_gb`; свободное место файловой системы учитывает их. Preflight — консервативная оценка, не резервирование диска: не запускайте параллельно другие большие загрузки. Одновременные запуски этого конвертера в одной папке `data_dir` блокируются.

## Поставка и воспроизводимость

`configs/datasets/datasets.json` содержит конкретные URL, опубликованные размеры и checksums. Hugging Face и GitHub URL закреплены за revisions. SJTU bags/GT закреплены опубликованными MD5; изменение содержимого останавливает загрузку. Checksums защищают от ошибки передачи, но MD5 не является криптографической гарантией происхождения.

Загрузки возобновляются через HTTP Range, `.part` не считается готовым файлом. Если сервер игнорирует Range, загрузка начинается заново. Неудачная проверка checksum не маскируется: остановка, без использования файла.

После подготовки:

```text
<data_dir>/
  raw/<sequence>/...                  # проверенные официальные исходники
  processed/<sequence>/
    mav0/
      cam0/data.csv                  # timestamp ns, filename
      cam0/data/<timestamp>.png      # uint8 grayscale
      cam0/sensor.yaml
      cam1/...                       # правая камера
      imu0/data.csv                  # ns, wx,wy,wz [rad/s], ax,ay,az [m/s²]
      imu0/sensor.yaml
    calibration/...                  # оригинальные калибровки/attributes
    reference/
      poses.tum                      # seconds, x,y,z,qx,qy,qz,qw
      metadata.json                  # происхождение, frames, transform к reference
      pose_covariance.csv            # только GrandTour
      prism_original.npz             # только GrandTour, POSITION-ONLY
    provenance.json                  # источники, revisions, hash конвертера
    validation.json                  # counts, интервалы, gaps, stereo time differences
    complete.json                    # создан только после успешной проверки
```

Это **EuRoC-подобная структура сенсоров**, не настоящий EuRoC ground-truth `state_groundtruth_estimate0`: velocity/bias GT не выдумываются. Reference остаётся отдельно с явной семантикой. Картинки переводятся в grayscale PNG; без resize, rectification, поворотов, изменения времени или потери кадров. У BotanicGarden используется уже уменьшенный официальный поток 960x600/10Hz, у GrandTour ZED2i — 1920x1080/15Hz. Depth не используется.

Файлы `sensor.yaml` содержат модель/искажения и `T_BS`, где **B — выбранный IMU**, S — сенсор, `p_B = T_BS @ p_S`. Это не готовые конфиги OpenVINS/VINS/ORB-SLAM: параметры шума, поддерживаемую модель, temporal calibration и настройки frontend нужно адаптировать отдельно. Для ADIS параметры шума не придуманы; для Xsens сохранены авторские параметры. Timestamp ns — формат хранения, не утверждение о наносекундной точности источника.

## Reference: нельзя смешивать происхождение и frames

**GrandTour**: stereo ZED2i + raw ADIS16475. Reference — `cpt7_ie_tc_odometry`, offline tightly coupled NovAtel Inertial Explorer; не ZED VIO, DLIO или onboard ANYmal odometry. Сохраняются source covariance и position-only призма. World frame из опубликованных attributes: `enu_origin`; tracked frame берётся из соответствующего CPT7 TF metadata. Для оценки IMU-траектории применяйте опубликованный `T_imu_reference`:

```text
T_world_reference(t) = T_world_imu(t) @ T_imu_reference
```

GrandTour ZARR transforms **не имеют обычного направления ROS TF**: в коде авторов metadata построены через `lookupTransform(child_frame_id, orig_frame)`. Конвертер инвертирует их и собирает цепочку до выбранного IMU. Не инвертируйте готовый `T_BS` повторно. Оригинальные attributes сохраняются.

**BotanicGarden**: gray stereo + Xsens. Берётся corrected `GT_pose_qnew.zip`, а не старый reference из VLIO bag. Траектория относится к VLP16, world остаётся sequence-local. Camera1 extrinsics собираются из gray0/Xsens и stereo calibration; независимо оцененные extrinsics gray1/Xsens также сохраняются в source calibration. Survey-map reference получен с VIO-assisted tracking/deskew: **не полностью независим от визуального метода**. Никакой общей регистрации последовательностей или выдуманного covariance не выполняется.

Reference не подаётся в VIO на вход. Не используйте `prism_original.npz` как 6DoF GT и не добавляйте к позиции единичные quaternion.

## Проверки и остающийся аудит

Конвертер проверяет checksums, безопасность архивов, наличие обоих image streams и raw IMU, конечность значений, строго возрастающее время, соответствие image/calibration resolution, quaternion norms и временное пересечение reference. Ошибки не исправляются сортировкой, фиктивными pose или заменой сенсора.

`validation.json` показывает максимальные gaps, nearest stereo timestamp difference, число кадров без IMU bracketing и **`usable_input_window_ns`**. На ALB-2 последние примерно 0.85s ZED-кадров выходят за опубликованный диапазон ADIS. Они сохранены и отмечены предупреждением. В runner выбирайте общий input interval из validation **одинаково для всех методов**, без экстраполяции IMU. Для оценки reference дополнительно нужна общая маска качества, построенная из covariance/quality и gaps, а не из ошибок метода.

Структурная проверка не доказывает физическую точность reference, корректность временной калибровки или успешность VIO. До benchmark нужно проверить реальный playback, timestamps/exposure, noise parameters и сформировать общий evaluation protocol. Данные полного image/bag recording при разработке не скачивались; тестировались синтетические записи обоих форматов, реальные небольшие ZARR sensor/reference archives и corrected GT bag.

## Первичные источники

- GrandTour: https://grand-tour.leggedrobotics.com/dataset
- Поставка: https://huggingface.co/datasets/leggedrobotics/grand_tour_dataset
- Примеры: https://github.com/leggedrobotics/grand_tour_dataset/tree/main/examples_hugging_face
- Metadata transforms: https://github.com/leggedrobotics/grand_tour_box/blob/main/box_utils/box_converter/huggingface-dataset-conversion/dataset_builder/build_metadata.py
- BotanicGarden: https://github.com/robot-pesg/BotanicGarden
- SJTU: https://scidata.sjtu.edu.cn/records/kfjy8-ex881

Условия использования исходных датасетов остаются авторскими. Скрипт не меняет лицензию данных; проверяйте её перед дальнейшим распространением.

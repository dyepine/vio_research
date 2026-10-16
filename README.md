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

## Настройки окружения

```bash
make configure  # один раз создаёт .envrc из scripts/env.sh
# Отредактируйте .envrc: VIO_DATA_DIR, VIO_RESULTS_DIR, VIO_EXPERIMENT_CONFIG,
# PIXI_BIN, PYTHON и другие настройки окружения.
```

`scripts/env.sh` — публичные defaults с комментариями. `.envrc` — локальный, игнорируется Git; существующий файл не перезаписывается даже при изменении defaults. Все команды Makefile сами читают `.envrc`, поэтому direnv и ручные `export` не обязательны. Если файла нет, он создаётся автоматически. Чтобы изменить общие defaults, редактируйте `scripts/env.sh`, а не `.envrc`. Локальных копий YAML больше нет.

`PYTHON` в `.envrc` выбирает интерпретатор для первоначального создания `.venv` (по умолчанию `python3`); существующее окружение автоматически не пересоздаётся. Для VSLAM-LAB используется Python из Pixi, а не этот интерпретатор. Служебные команды, зависимости и фиксированный путь `.venv` остаются в Makefile.

`.envrc` выполняется как shell-код: используйте только доверенный файл. Клонирование и `make configure` не устанавливают Pixi или окружения VSLAM-LAB.

## Запуск ORB-SLAM3 через VSLAM-LAB

Из корня проекта: `make run`. Makefile читает пути Pixi, кеша и число потоков из `.envrc`; ручные `export` и переход в каталог VSLAM-LAB не нужны. Требуются уже установленный Pixi (`PIXI_BIN`) и окружения VSLAM-LAB.

Выбранный YAML эксперимента задаётся через `VIO_EXPERIMENT_CONFIG` в `.envrc` (по умолчанию `configs/experiments/grandtour_alb2_orbslam3.yaml`). Можно указать абсолютный путь или путь относительно корня проекта; обвязка по-прежнему поддерживает один эксперимент и одну последовательность. YAML ссылаются на `${VIO_DATA_DIR}` и `${VIO_RESULTS_DIR}` из `.envrc`. `VIO_RESULTS_DIR` — постоянный корневой каталог результатов. Каждый `make run` создаёт внутри него отдельную папку по локальной дате и времени, например `2026-10-12_21-30-00`; при совпадении времени добавляется суффикс `-02`, `-03` и т. д. Переименовывать каталоги или менять `.envrc` перед каждым запуском не нужно. Старые результаты не перезаписываются. Проверки камер/IMU выполняются автоматически; путь нового запуска печатается в терминале, native log и отчёты сохраняются внутри него.

`scripts/run_grandtour_alb2.py` — внешняя обвязка существующих API VSLAM-LAB, не альтернативная реализация алгоритма. Она задаёт пути на отдельных объектах датасета/эксперимента, не меняя файлы фреймворка или его глобальные константы. Входы остаются в формате VSLAM-LAB: `rgb.csv`, `imu_0.csv`, `calibration.yaml` и каталоги изображений. Подготовку экспериментальных CSV/калибровки, команду запуска и защиту RAM выполняет VSLAM-LAB. Проверка окна камер/IMU вынесена в `scripts/check_vio_inputs.py`. Эталон GNSS/INS не читается при запуске и должен проверяться отдельно перед оценкой; оценка выполняется отдельно через evo без коррекции масштаба.

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

Активные последовательности и лимиты находятся в **`configs/datasets/prepare.yaml`**, папка данных — в `.envrc`:

```yaml
data_dir: ${VIO_DATA_DIR}
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

**YAML задаёт последовательности и лимиты, `.envrc` — машинные пути.** В полях путей YAML поддерживаются явные `${VARIABLE}`; отсутствие указанной переменной вызывает ошибку. Никаких скрытых переопределений параметров алгоритма через окружение нет. Старые make-параметры `DATA_DIR`, `SEQUENCES`, `MAX_DATA_GB`, `RESERVE_GB` и соответствующие CLI-флаги больше не поддерживаются.

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

## Оценка и просмотр результатов через evo

```bash
make evaluate RUN_DIR=/path/to/run
make visualize RUN_DIR=/path/to/run
make visualize VIS_ARGS="--evaluation-dir /path/to/run/evaluations/<date> --save /tmp/comparison.rrd"
```

Без `RUN_DIR` выбирается последний датированный запуск. Внутри него `visualize`
выбирает последнюю завершённую оценку, пропуская папки прерванного сохранения.
`evaluate` и `visualize`
используют отдельное `.venv-rerun` с закреплёнными evo 1.35.2 и Rerun 0.31.4;
окружение алгоритма VSLAM-LAB и его lockfile не меняются. Для этого окружения
Makefile очищает `PYTHONPATH`, чтобы системные ROS-пакеты не попадали в оценку. `make test` проверяет
также интеграцию оценки и headless-экспорт Rerun.

`Evaluation` в YAML эксперимента сохраняется в `run_provenance.json` при запуске.
Оценка читает этот снимок, а не текущий конфиг. Для старого запуска без снимка
или отдельного протокола используйте `EVAL_ARGS="--protocol /path/to/evaluation.yaml"`:
файл содержит только mapping полей `Evaluation`. Другой GT можно явно задать
через `EVAL_ARGS="--gt /path/to/groundtruth.csv"`.

Каждая оценка создаёт отдельный `evaluations/<date>/` с `protocol.yaml`,
`summary.json` и стандартными ZIP evo: `ape_position_m`, `ape_orientation_deg`,
`rpe_position_m`, `rpe_orientation_deg`. ZIP сохраняют статистику и ошибки;
APE ZIP также содержит сопоставленные выровненные траектории. Их можно читать
через evo и сравнивать через `evo_res`. Rerun показывает сохранённые результаты
без чтения исходных CSV и пересчёта. Повторная оценка не перезаписывает прежнюю.

Протокол: SE(3) либо отсутствие выравнивания, без scale correction;
Стандартный `evo.sync.associate_trajectories` с допуском 0.01 s: для каждой
позы траектории с меньшим числом поз выбирается ближайшая поза другой траектории.
Повторное использование поз допускается. Отчёт разделяет число пар и число
уникальных сопоставленных estimate/GT-поз; доля оценённых сохранённых поз
считается по уникальным estimate-позам. `matched_poses` сохраняется как прежнее
имя числа пар, равное `matched_pairs`.
Экстраполяция за временные границы GT запрещена.
Наносекунды читаются как int64; общий origin вычитается до перевода в секунды.
Quaternion CSV имеет порядок xyzw, evo — wxyz: это не EuRoC GT CSV.

`estimate_frame: camera` и `camera: rgb_0` задают преобразование через
`T_WB = T_WC @ inverse(T_BC)`. Перед оценкой нового алгоритма подтвердите
семантику его экспортированной позы; для body-позы задайте `estimate_frame: body`.
`evaluate_orientation: true` требует 6DoF-эталон; identity-only orientation
вызывает ошибку. Для проверенного position-only reference можно явно отключить
ориентационные метрики, согласовав физическую точку сравнения.

RPE использует пары по расстоянию GT: `rpe_delta_m: 1.0`, относительный допуск
`rpe_relative_tolerance: 0.1`, все подходящие пары. Пары не пересекают разрывы
более `max_pose_gap_s: 1.0`. Rerun показывает полные статические ломаные через
сопоставленные сохранённые позы, а длинные промежутки отмечает серыми маркерами.
Интервалы, исключённые маской качества GT, ломаная не соединяет. Этот порог —
правило сегментации сохранённых keyframes, а не детектор tracking loss.
При отсутствии подходящих пар RPE отмечается как недоступная, без фиктивных нулей.

Опциональный `gt_valid_intervals_ns: [[start_ns, end_ns], ...]` задаёт общие
интервалы качества GT. Они должны быть упорядочены и не пересекаться; границы
включены, исключённые интервалы не соединяются RPE. Маску следует выбирать по
качеству эталона, а не ошибкам метода. Без маски качество GT не сертифицируется.

Оцениваются сохранённые keyframes. `summary.json` отдельно показывает статус
запуска, число сопоставленных поз, временные разрывы и предупреждения native log.
Временной размах не выдаётся за полноту обработки изображений. Несколько карт
по native log отклоняются; parsing логов не является полной диагностикой resets.
Незавершённый запуск допускается только как явно отмеченный частичный результат.

Runner сохраняет журнал `vslamlab_exp_log.csv` в формате VSLAM-LAB; после оценки
он получает `EVALUATION=evo` и путь к артефактам. Встроенный evaluator VSLAM-LAB
с захардкоженным Sim(3) не вызывается. Его старые plot/compare-команды не являются
автоматически совместимыми с новым расположением оценок; сравнение метрик — через evo.

Rerun использует мост evo для точек, линий, residuals и графиков ошибок.
Отправка ориентаций — небольшой локальный адаптер: в evo 1.35.2 мост
переставляет quaternion по плоскому массиву вместо оси каждой позы.
Исправление представления проверяется отдельно; метрики остаются расчётом evo.

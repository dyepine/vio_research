# Историческая инструкция

Снимок README до подготовки сдачи 2026-10-19. Описывает прежние defaults,
локальные пути и старые статусы публикации; для актуального запуска см. [README](../README.md).

# VIO research

Подготовка и запуск используют стандартный lifecycle VSLAM-LAB.
План и состояние переезда: [docs/dataset-migration.md](docs/dataset-migration.md).

## Чистая машина

Поддерживается Linux x86_64; нужны `git`, `make`, `curl`, `tar`, `sha256sum`
(обычные системные утилиты). Системный ROS и ручная установка Python-пакетов не нужны.
После checkout репозитория:

```bash
make prepare
make run
```

`make prepare` сам инициализирует закреплённый submodule, устанавливает локальный
Pixi 0.81.0 с проверкой SHA-256 и окружения из `pixi.lock`,
скачивает и готовит **все четыре выбранные записи**:
GrandTour `kaeb_1`, `alb_1`; BotanicGarden `1018_00`, `1018_13` вместе с corrected GT.
Список — `configs/datasets/selected.yaml`. Каталог адаптера содержит все 10 публичных
BotanicGarden-записей с bags и corrected GT: `1005_00`, `1005_01`, `1005_05`,
`1005_07`, `1006_01`, `1006_03`, `1008_01`, `1008_03`, `1018_00`, `1018_13`.
Расширение каталога не расширяет выбор для скачивания: у нас остаются две `1018`-записи.
Чтобы выбрать другую опубликованную запись, укажите её в selection YAML.
Для трёх дополнительных bags checksum — SHA-256 из OneDrive metadata;
для остальных bags и corrected GT сохранены MD5. Другие 23 записи авторы
предоставляют по запросу, публичные download URLs для них не указаны. `lmb_2`, `hoeb_1` и прежняя `alb_2`
не включены в основной набор.

По умолчанию данные лежат в `$HOME/datasets/vio_research`. Для SSD:

```bash
VIO_DATA_DIR=/path/to/ssd/vio_research/data make prepare
VIO_DATA_DIR=/path/to/ssd/vio_research/data make run
```

Пути можно сохранить в `.envrc`, которую `make` создаёт и не перезаписывает.
Локальная `.envrc` этой машины уже указывает на `/media/napalkov/T7/vio_research/data`.
`BOTANICGARDEN_SOURCE_DIR` позволяет переиспользовать скачанные bags/GT; `.part`
докачивается на месте. Bags и corrected GT скачиваются сразу с официального
OneDrive, без обращений к SJTU. Подписанный download URL обновляется при каждой
попытке. Обрывы допускаются, пока сохранённый файл растёт; 10 ошибок подряд
без прогресса останавливают загрузку с сохранением `.part`.
Полный размер и MD5 обязательны. Повтор той же команды не требует ручного распаковывания.
В терминале `make prepare` показывает `tqdm` progress bar: процент, объём, скорость
и ETA. При докачке учитывается сохранённая часть; проверка MD5 имеет отдельный
индикатор. При перенаправлении в файл динамические бары отключены, остаются
сообщения о запросах, ошибках и завершении.
Доступность и скорость внешних зеркал остаются ограничением.

Адаптер BotanicGarden и необходимые исправления ROS/download helpers находятся
в нашем [fork VSLAM-LAB](https://github.com/dyepine/VSLAM-LAB/tree/vio-research-datasets).
Точная ревизия submodule хранится в gitlink `external/VSLAM-LAB`
(`git rev-parse HEAD:external/VSLAM-LAB`). Новые интеграции собраны в локальной
ветке `integration/feature-history` обоих репозиториев; они ещё не опубликованы.
Для checkout на другой машине сначала нужно опубликовать коммиты fork, затем
основного репозитория. Адаптеры входят в исходники fork; отдельные патчи
при bootstrap не применяются. Bootstrap читает pin из Git,
при несовпадении ревизии сохраняет checkout и останавливается.
Исходный `VSLAM-LAB/VSLAM-LAB` остаётся источником обновлений. Отправка PR
в upstream не входит в эту работу. Обновление fork и pin требует проверки
совместимости адаптера и повторного запуска тестов.

## Конфигурация и запуск

GEODE **Offroad1 γ** доступен отдельным выбором:
`make prepare CONFIG=configs/datasets/geode.yaml`. Адаптер `geode-gamma` готовит
ректифицированное stereo + внешний Xsens IMU; исходный bag — около 3,2 GB.
Конвенции калибровки и ограничения GT описаны в [docs/GEODE.md](docs/GEODE.md).

Для sqrtVINS добавлен `configs/experiments/geode_sqrtvins.yaml`;
сборка, запуск и ограничения первых проверок описаны в [docs/SQRTVINS.md](docs/SQRTVINS.md).

SchurVINS stereo-VI запускается через `configs/experiments/geode_schurvins.yaml`;
адаптер и результаты GEODE описаны в [docs/SCHURVINS.md](docs/SCHURVINS.md).

`configs/datasets/selected.yaml` — список скачиваемых записей в штатном формате
VSLAM-LAB `dataset: [sequence, ...]`. Его читает `make prepare`, который также
проверяет подготовленные данные. Запас места — 15 GB, лимит каталога данных — 125 GB;
проверка места не резервирует диск. При подготовке по файлу эксперимента можно
переопределить бюджеты через необязательный `Preparation: {reserve_gb: 15, max_data_gb: 125}`.

`configs/experiments/comparison.yaml` — один файл эксперимента:

```yaml
Datasets:
  grandtour-alphasense: [kaeb_1]
  botanicgarden: ['1018_00']
Methods:
  orbslam3_default:
    Module: orbslam3
    Parameters: {mode: stereo-vi, verbose: 0}
    Evaluation: {estimate_frame: camera, camera: rgb_0}
  orbslam3_no_loop:
    Module: orbslam3
    Parameters: {mode: stereo-vi, verbose: 0}
    Evaluation: {estimate_frame: camera, camera: rgb_0}
    Settings: {loopClosing: 0}
NumRuns: 1
Evaluation:
  align: origin
  correct_scale: false
  max_time_difference_s: 0.01
```

Каждый вариант `Methods` запускается на каждой записи `Datasets` с `NumRuns`
повторами. В примере — четыре запуска. Варианты имеют отдельные логи и результаты.
`Parameters` — параметры запуска VSLAM-LAB; `Settings` переопределяет только
указанные ключи штатного YAML метода. Калибровка камер/IMU берётся из датасета.
Без `Settings` применяется штатный файл метода. Viewer по умолчанию выключен
(`verbose: 0`); при первом запуске VSLAM-LAB устанавливает метод и vocabulary/weights.

```bash
make run                                      # вся матрица comparison.yaml
make run CONFIG=configs/experiments/comparison.yaml
make run RGB_MAX=200                           # короткая проверка всей матрицы
make run PLAN=1                                # native YAML без запуска методов
make prepare CONFIG=configs/experiments/comparison.yaml # только записи эксперимента
```

Основной `comparison.yaml` сравнивает ORB-SLAM3 mono-vi, ORB-SLAM3 stereo-vi
и OKVIS2 mono-vi без замыкания петель на GrandTour и BotanicGarden.
ORB stereo-vi использует обе камеры; остальные варианты — `rgb_0` и IMU.

Для текущих данных используйте подготовленные копии с исправлением парсинга OKVIS2:

```bash
python3 results/vio/orbslam3_okvis2_inputs_20261013/prepare.py
VIO_DATA_DIR="$PWD/results/vio/orbslam3_okvis2_inputs_20261013" \
  make run
```

В этом конфиге `Parameters.imu_noise_by_dataset` задаёт общий профиль шума
для всех трёх вариантов: опубликованную Allan-калибровку GrandTour и рабочий
профиль ORB-SLAM3 авторов BotanicGarden. Профиль фиксируется как `imu_noise`
в каждом native recipe и применяется только к `calibration_exp.yaml` запуска.
Скрипт подготовки сохраняет обход ошибки парсера OKVIS2 на семи субнормальных
числах гироскопа BotanicGarden; исходные данные на T7 сохраняются.
После запуска оценивайте новую папку командой
`make evaluate RUN_DIR=/path/to/new/comparison EVAL_ARGS=--saved-protocol`.

Для оригинального **OKVIS 1 stereo-inertial** добавлен отдельный baseline и конфиг:

```bash
make run CONFIG=configs/experiments/okvis1_stereo_vi.yaml RGB_MAX=200
make evaluate RUN_DIR=/path/to/new/comparison EVAL_ARGS=--saved-protocol
```

Сборка и поддерживаемые входы описаны в [docs/OKVIS1.md](docs/OKVIS1.md).

Сравнение ORB-SLAM3, OKVIS 1 и Voxel-SVIO на GrandTour `kaeb_1`
и BotanicGarden `1018_13`, без `FrameStart`:

```bash
make run CONFIG=configs/experiments/orbslam3_okvis1_voxel_svio.yaml JOBS=3
make evaluate RUN_DIR=/absolute/path/to/new/comparison EVAL_ARGS=--saved-protocol
```

`JOBS=3` запускает методы параллельно. Общий протокол и интеграция Voxel-SVIO
описаны в [docs/VOXEL_SVIO.md](docs/VOXEL_SVIO.md).

Для сравнения ORB-SLAM3 и PyCuVSLAM со стереопарой и IMU используйте
`configs/experiments/orbslam3_pycuvslam_stereo_vi.yaml`:

```bash
make run CONFIG=configs/experiments/orbslam3_pycuvslam_stereo_vi.yaml
make evaluate RUN_DIR=/path/to/new/comparison EVAL_ARGS=--saved-protocol
```

Это четыре запуска: оба метода на GrandTour `kaeb_1` и BotanicGarden
`1018_13`, по одному повтору, без loop closure. `FrameStart.botanicgarden.'1018_13': 20`
задаёт общий старт с кадра 20 (индекс с нуля), после начальной адаптации экспозиции;
окно по-прежнему ограничивается доступностью IMU. Исходные данные сохраняются.
Рабочие профили шума IMU общие
для обоих методов: исторический проверенный профиль GrandTour и профиль
ORB-SLAM3 авторов BotanicGarden. Это настройки оценивателей, а не утверждение
о измеренном шуме сенсоров. PyCuVSLAM экспортирует позу rig в системе левой
камеры; оценка обоих методов использует `estimate_frame: camera`, `rgb_0`.
Отказы и неполные траектории необходимо учитывать вместе с APE/RPE.

DROID-SLAM подключён отдельным stereo-экспериментом
`configs/experiments/droidslam_stereo.yaml` (GrandTour `kaeb_1`, BotanicGarden
`1018_13`, старт BotanicGarden с кадра 20):

```bash
make run CONFIG=configs/experiments/droidslam_stereo.yaml RGB_MAX=100
make evaluate RUN_DIR=/path/to/new/comparison EVAL_ARGS=--saved-protocol
```

Используется штатный Pixi-пакет `droidslam` 1.2 и веса VSLAM-LAB.
Метод использует только стереокамеры, без IMU. Локальный stereo entry point
в `external/VSLAM-LAB/Baselines/extra-files/droidslam/` исправляет fisheye
ректификацию GrandTour, перевод внутренних единиц DROID (стереобаза 0,1 м)
в метры по калибровке, ориентацию исходной левой камеры, сохранение int64
timestamps и разбор `upsample: 0`. Оценка использует `rgb_0`, без подгонки масштаба.
Конфиг уменьшает буфер до 256 ключевых кадров для 6 GB GPU; это не скользящее
окно. При заполнении буфера запуск явно завершается с ошибкой. Проверка
на 100 кадрах не подтверждает работу полной записи; для длинного запуска
могут понадобиться больший GPU/буфер. Адаптер включён в закреплённый локальный коммит submodule;
публикация новых коммитов fork пока не выполнена.

`METHOD`/`MODE` перенесены в файл эксперимента. Без `CONFIG` подготовка читает
`VIO_DATASET_CONFIG` (`selected.yaml`), запуск — `VIO_EXPERIMENT_CONFIG`
(`comparison.yaml`). Машинные пути остаются в `.envrc`.
`run_catalog.py` проверяет подготовленные входы и окно IMU, генерирует native YAML,
затем вызывает штатные `run_exp`/`run_sequence`. Исходный файл эксперимента,
эффективные настройки всех вариантов, протокол оценки и аудит входов сохраняются
в `${VIO_RESULTS_DIR}/VSLAM-LAB-Evaluation/comparison_.../inputs/`.
Каждый `make run` создаёт одну папку для всей матрицы: `experiment.yaml` и
`comparison.csv` лежат в её корне, результаты вариантов — внутри этой же папки.
Штатный `VSLAMLAB_EVALUATION` указывает на эту папку только для текущего процесса.
Повторный запуск создаёт новую папку и сохраняет предыдущие результаты.

```text
comparison_<timestamp>_<id>/
  experiment.yaml
  comparison.csv
  inputs/
  orbslam3_mono_no_loop_0/
  orbslam3_mono_no_loop_1/
  orbslam3_stereo_no_loop_0/
  orbslam3_stereo_no_loop_1/
  okvis2_no_loop_0/
  okvis2_no_loop_1/
```

Существующие матрицы на этой машине перенесены в эту структуру. Ранние одиночные
проверки сохранены отдельно в `${VIO_RESULTS_DIR}/legacy-catalog-runs/`.
Прежнее плоское расположение больше не поддерживается командами запуска и оценки.

`PLAN=1` может установить метод для получения его штатного файла настроек.
Конвертация выполняется в `dataset.download_sequence`, отдельной команды convert нет.

Оценка всей сохранённой матрицы выполняется штатным `evaluate_exp` из нашего
форка VSLAM-LAB, в том же Pixi-окружении, что и запуск:

```bash
make evaluate                                  # последняя запущенная матрица, PLAN пропускается
make evaluate RUN_DIR=/path/to/comparison_...   # конкретная сохранённая матрица
make evaluate EXPERIMENT=/path/to/comparison_.../experiment.yaml
```

Протокол `Evaluation` задаёт выравнивание, допуск времени и APE/RPE.
Общие настройки применяются ко всем вариантам; `Methods.<variant>.Evaluation`
переопределяет их для конкретного метода. `estimate_frame: camera` вместе с
`camera: rgb_0` означает экспорт позы камеры — оценщик переводит её в body/IMU
через сохранённую калибровку. Для экспорта позы корпуса укажите
`estimate_frame: body`; преобразование камеры тогда не применяется.
Для ORB-SLAM3 в текущих вариантах явно указан экспорт камеры.

Для каждого повтора сохраняются immutable `summary.json`, `protocol.yaml` и
стандартные ZIP evo в `<native output>/evaluations/<iteration>/<timestamp>/`.
После оценки автоматически создаётся `<comparison>/figures/`: для каждой записи
два листа в PNG и PDF — XY-маршрут (`*_trajectories`) и четыре графика ошибок
позиции/ориентации APE/RPE со сводной таблицей (`*_errors`).
Маршрут содержит полный GT серым фоном, общий GT оцениваемого участка пунктиром
и все сохранённые позы методов. Используется сохранённое преобразование evo,
без нового fit; масштабы X/Y одинаковы. Временные ошибки берутся из ZIP evo;
RPE all_pairs показывается точками. Таблица содержит четыре RMSE, покрытие,
число сопоставленных/сохранённых поз и статус, включая неудачные запуски.
На странице помещается до четырёх запусков (метод + повтор); при большем числе
добавляется суффикс `_pNN`. Цвета и пределы осей сохраняются между страницами.
Полная таблица записи сохраняется в `*_summary.csv`.
Картинки обновляются вместе с последней таблицей, версии самих оценок сохраняются.

Общая таблица — `<comparison>/comparison.csv`: отдельная строка для каждого
запуска, ошибки позиции/ориентации, число пар, доля сопоставленных сохранённых поз
и статус. Неудачные запуски остаются строками таблицы; команда возвращает ошибку.
`compare_exp` для экспериментов с `Evaluation` собирает ту же таблицу по сохранённым
оценкам. Запуски разных последовательностей не усредняются в общий рейтинг.
Повторная оценка сохраняет новую версию и обновляет ссылки в native логе.

Допуск времени задаётся в `Evaluation` и не увеличивается автоматически при низком покрытии.
Метрики описывают сохранённые позы, а не все входные изображения. Native YAML без
`Evaluation` сохраняет прежний benchmark-путь VSLAM-LAB с Sim(3); наши сгенерированные
эксперименты всегда содержат явный протокол без коррекции масштаба.
`make run` сохраняет протокол, а оценка запускается отдельной командой.

Старые research runs можно переоценивать тем же кодом `Evaluate`:

```bash
make evaluate RUN_DIR=/path/to/research_run
```

Новые запуски создаёт только `make run`. Все тесты выполняются в Pixi:

```bash
make test
```

Корневые `evaluate_result.py`, `trajectory_inputs.py` и `run_results.py` делегируют
работу модулю `Evaluate`; независимой реализации метрик в корневом репозитории нет.

## Формат и источники

```text
${VIO_DATA_DIR}/VSLAM-LAB-Benchmark/<DATASET>/<sequence>/
  rgb_0/, rgb_1/
  rgb.csv
  imu_0.csv
  calibration.yaml
  groundtruth.csv
  preparation_report.json
```

GrandTour использует штатный `grandtour-alphasense`: global-shutter камеры и
BMI085. Основные записи — KÄB-1 и ALB-1. Стандартный resize `[640,480]` сохраняет
пропорции. Для наших outdoor-записей проверяется наличие GNSS/INS
`cpt7_ie_tc_odometry`; prism-only fallback не принимается как 6DoF GT.
HF revision данных штатным адаптером не закрепляется; это отмечено в provenance.

BotanicGarden использует VLIO bags и corrected `gt_<sequence>_qnew.bag` с OneDrive и
калибровку из закреплённого GitHub revision. Bags и GT проверяются по MD5.
Native gray stereo — 960×600/10 Hz; Xsens IMU — nominal 400 Hz.
Извлечение использует `header.stamp`, стереопары сопоставляются по одинаковому
времени. Corrected GT VLP16 приводится к Xsens:
`T_world_xsens = T_world_vlp16 @ inverse(T_xsens_vlp16)`.

Исходный GT сохраняется в `groundtruth_vlp16.csv`. Позы с NaN/Inf исключаются
без интерполяции; их timestamps перечислены в `reference_metadata.json`.
В реальной `1018_00` обнаружена одна такая поза. Reference использует
VIO-assisted tracking и не полностью независим от визуального метода.
Исходные bags, GT и калибровка сохраняются. Прерванный собственный импорт
BotanicGarden возобновляет hooks; неизвестные частичные каталоги не перезаписываются.

`make test` проверяет миграцию, окружение, входы runner и evaluator.
Успешная подготовка не доказывает успешность VIO. На нестабильном T7 реальные
прогоны не запускать; локальная проверка импорта выполнена на внутреннем NVMe.

## Состояние миграции

Адаптер BotanicGarden опубликован в закреплённом fork/submodule VSLAM-LAB;
чистый checkout получает его через автоматический bootstrap.
Старый EuRoC-like exporter, manifest, storage YAML и его тесты удалены после
проверки BotanicGarden, KÄB-1 и ALB-1. `zarr`, `numcodecs`, `rosbags`, `requests`,
`scipy`, `Pillow` больше не устанавливаются отдельным bootstrap-окружением;
подготовка, методы, оценка и тесты используют Pixi VSLAM-LAB. Уже установленные окружения и
данные не удалялись. Историческая инструкция — [здесь](docs/legacy-dataset-preparation.md).

## Оценка результатов через evo

```bash
make evaluate
make evaluate RUN_DIR=/path/to/comparison_or_research_run
```

Без `RUN_DIR` выбирается последняя запущенная native comparison.
Оценка и её тесты используют окружение Pixi VSLAM-LAB; `make evaluate`
создаёт PNG/PDF и таблицы сравнения. Отдельного окружения просмотрщика нет.

Для native comparison `make evaluate` читает параметры сравнения из `Evaluation`
текущего конфига (`CONFIG=...` или `VIO_EXPERIMENT_CONFIG`), включая настройки
`Methods.<variant>.Evaluation`. Семантика экспортированной позы (`estimate_frame`,
`camera`), траектории, GT и калибровка берутся из сохранённого запуска.
Команда печатает путь запуска, конфиг, выравнивание и допуск времени.
Каждая версия оценки сохраняет фактически использованный протокол.
`EVAL_ARGS="--saved-protocol"` воспроизводит настройки запуска;
`--protocol /path/to/protocol.yaml` задаёт явные переопределения поверх выбранных настроек.
Research runs продолжают использовать сохранённый `run_provenance.json`;
для старого запуска без протокола требуется явный `--protocol`.
Другой GT можно задать через `EVAL_ARGS="--gt /path/to/gt.csv"` для research run.

Каждая оценка создаёт отдельный `evaluations/<date>/` с `protocol.yaml`,
`summary.json` и стандартными ZIP evo: `ape_position_m`, `ape_orientation_deg`,
`rpe_position_m`, `rpe_orientation_deg`. ZIP сохраняют статистику и ошибки;
APE ZIP также содержит сопоставленные выровненные траектории. Их можно читать
через evo и сравнивать через `evo_res`. Повторная оценка не перезаписывает прежнюю.

В текущем эксперименте `align: origin`: штатный evo совмещает первую
сопоставленную body-позу с GT по положению и ориентации после association.
Преобразование фиксируется для всего участка; последующий дрейф не подгоняется.
Также доступны `align: SE3` (fit по всем позициям) и `align: none`.
Начало означает первую сопоставленную позу, а не первый входной кадр.
Масштаб не корректируется; origin требует полноценной ориентации GT.
Стандартный `evo.sync.associate_trajectories` с заданным `max_time_difference_s`: для каждой
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
более `max_pose_gap_s: 1.0`. На графиках траекторий не соединяются длинные
разрывы и интервалы, исключённые маской качества GT. Этот порог —
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

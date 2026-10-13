## Компактная конфигурация экспериментов

`configs/datasets/selected.yaml` — список скачиваемых записей.
`configs/experiments/comparison.yaml` — Datasets, Methods, NumRuns и Evaluation.
Параметры метода переопределяются через Parameters и Settings; остальное берётся
из каталога. Конфиги отдельных пар и полный локальный ORB-SLAM3 YAML удалены.
Штатный run_exp поддерживает необязательный MethodSettings для каждого
сгенерированного native experiment; установка, повторы и логи остаются штатными.
Исследовательский запуск выбирает одну запись и вариант из того же файла.
Ниже — исторический журнал миграции; прежние команды и конфиги заменены этой схемой.

# Переезд подготовки датасетов на VSLAM-LAB

Дата решения: 2026-10-12. Актуальная цель уточнена 2026-10-13: `make prepare`
на чистой Linux x86_64 машине и штатный pipeline `make run METHOD=... MODE=...`.
KÄB-1, ALB-1 и BotanicGarden 1018_00 подготовлены; 1018_13 ещё загружается.
По последнему решению пользователя от 2026-10-13 адаптер поставляется через
fork `dyepine/VSLAM-LAB`, ветка `vio-research-datasets`, submodule commit
`219df9d6667817db42e7b7a1db902fc7825807ea`. Патч и его применение удалены.
Отправка изменений в upstream не планируется.
Этот документ определяет целевую подготовку данных; старые попытки ALB-2 в
`PLAN.md` остаются историей эксперимента, а не обязательным выбором новых записей.

## Решение и границы

Использовать стандартный формат и жизненный цикл `DatasetVSLAMLAB` для обоих
датасетов. Для GrandTour использовать готовый `grandtour-alphasense`, для
BotanicGarden добавить штатный адаптер. Собственный EuRoC-подобный промежуточный
экспорт и GrandTour ZED2i + ADIS выводятся из эксплуатации.

Уточнение от 2026-10-13: для выбранных GrandTour-записей используем штатный
GNSS/INS GT из `cpt7_ie_tc_odometry`, с преобразованием в body frame Alphasense.
В отчётах ATE/RPE явно указывать этот источник. Импорт VSLAM-LAB не объединяет
его с призмой; Holistic Fusion не является эталоном этого эксперимента.
Отдельную подготовку призмы, восстановление её extrinsics и генерацию Holistic
Fusion не включаем в переезд и не требуем для приёмки. Если штатный адаптер
скачивает prism-поток, это не повод менять его: дополнительный поток может
оставаться в стандартной поставке, но не участвует в нашей оценке.

Локальное [сравнение ALB-2](../results/gnss-prism-alb2-20261013/REPORT.md)
сохраняется как дополнительная диагностика: после SE(3)-выравнивания RMSE
расхождения позиций 0,385 м, при допущении о плече призмы из опубликованной
модели Boxi. Калибровка призмы конкретной миссии не подтверждена, поэтому число
не является доказанной ошибкой GNSS и не переносится на KÄB-1/ALB-1.
Артефакты анализа локальные, в игнорируемом `results/`; доступность этого отчёта
не является условием воспроизводимости импорта из чистого checkout.

GNSS covariance не входит в текущие ATE/RPE. Дополнительная загрузка GNSS-потоков,
взвешенные метрики и автоматическая маска по неопределённости в этот переезд не
входят. Неточность GT всё равно ограничивает трактовку результатов: численное
расхождение с GT не обязательно целиком является ошибкой VIO.

Сохраняем текущую оценку через evo: SE(3) без коррекции масштаба, явное временное
сопоставление, отдельные метрики положения/ориентации, RPE внутри непрерывных
участков. Стандартный импорт не означает переход на штатный evaluator VSLAM-LAB,
который в закреплённой версии использует `-as`.

## Какие записи GrandTour оставляем

Все новые входы — передняя stereo-пара Alphasense + её BMI085 IMU; ZED2i не используется.
Названия ниже — реальные ключи `grandtour-alphasense`, а не имена нашего старого экспортера.

| Запись | HF mission | Роль после переезда | Основание |
|---|---|---|---|
| `kaeb_1` (KÄB-1) | `2024-11-14-14-36-02` | Основная, первая для проверки переезда | Лес/трава/тропа; наименьшая опубликованная GNSS/INS-неопределённость среди проверенной четвёрки |
| `alb_1` (ALB-1) | `2024-11-15-11-18-14` | Вторая основная | Лес/грунт/тропа; короткая запись, присутствуют люди; GT менее уверенный, чем KÄB-1 |
| `lmb_2` (LMB-2) | `2024-11-15-14-43-52` | Дополнительная, выключена по умолчанию | Ещё один лесной маршрут; GNSS/INS-неопределённость порядка метров |
| `hoeb_1` (HÖB-1) | `2024-11-14-11-17-02` | Сложный случай для устойчивости, выключена по умолчанию | Частичный GNSS и многометровая неопределённость GT; не включать в общий рейтинг точности без пояснения |
| RIV-1 | `2024-11-04-16-52-38` | Исключена из текущего пути | В HF есть только карта, нет потоков камер/IMU; штатный адаптер её не поддерживает |

ALB-2 (`alb_2`) уже подготовлена: данные и результаты сохраняются как прежний
эксперимент, но запись не включается автоматически в новый основной набор.
ALB-3, TRIM-1, ROOT-1 и CYN-1/2 не добавляются в рамках этого переезда.
Основной список `configs/datasets/selected.yaml` содержит KÄB-1, ALB-1 и обе
BotanicGarden-записи. Один запуск выбирает одну запись; методы берутся из каталога.

RIV-1 исключается из HF/VSLAM-LAB-пути, а не объявляется отсутствующей во всех
форматах. Ради неё отдельный путь ROS/Kleinkram сейчас не добавляется.

Условия и покрытие тахеометром сверены с [таблицей миссий GrandTour](https://arxiv.org/html/2602.18164v1#S4).
При анализе четырёх записей медиана `sqrt(sigma_x² + sigma_y² + sigma_z²)` из
`gnss_raw_cpt7_ie_tc/position_ecef_std` составила: KÄB-1 — 0,014 м,
ALB-1 — 0,426 м, LMB-2 — 1,369 м, HÖB-1 — 2,745 м. Это собственная оценка
неопределённости GNSS/INS, не измеренная ошибка. Проверенная HF revision:
`daf91c5e2b6db564822a35cc58222d73f8e75bab`. `pose_cov` в odometry нулевой во
всех 40 доступных потоках этой поставки. Данные неопределённости не исчезли
вообще: они есть в соседних GNSS-потоках.

## Один путь подготовки и запуска

Целевая цепочка:

```text
make prepare -> выбранные dataset/sequence -> get_dataset(...)
             -> dataset.download_sequence(sequence)
             -> VSLAM-LAB-Benchmark/<DATASET>/<sequence>/
make run     -> тот же dataset/sequence -> проверка камер/IMU -> baseline
make evaluate -> сохранённая траектория + GT -> текущий протокол evo
```

- Machine paths остаются в `.envrc`: `${VIO_DATA_DIR}`, `${VIO_RESULTS_DIR}`, Pixi.
- Корни задаются через environment overrides `VSLAMLAB_BENCHMARK` и
  `VSLAMLAB_EVALUATION`, чтобы штатный pipeline и вспомогательные команды видели
  те же данные на SSD. `path_constants.py` автоматически не переписывается;
  поддержка environment входит в fork, upstream defaults сохранены.
- Выбор записей — единый YAML в формате VSLAM-LAB. Подготовка не имеет своей
  несовместимой системы имён и отдельного флага активности тех же записей.
  Подготовка читает YAML, на который ссылается эксперимент; для нескольких
  отдельных экспериментов общий список представляет объединение их входов.
- Удалить зависимость runner от `StorageConfig: configs/datasets/prepare.yaml`:
  получать корень данных из `.envrc`. Только после этого старый storage YAML
  можно убрать. Настройки алгоритма и оценки остаются в эксперименте.
- `make prepare` вызывает штатную полную подготовку. Смысл команды VSLAM-LAB
  `download_sequence` включает конвертацию, а не только получение архивов.
  Старые `download`/`convert` не сохранять как вводящие в заблуждение алиасы;
  убрать после обновления README/help. Отдельная проверка входов остаётся.
- Стандартные resolution/retention VSLAM-LAB явно фиксировать в отчёте подготовки.
  Для GrandTour принять штатный `target_resolution: [640, 480]` с сохранением
  пропорций. Это не обязательно точные 640×480 и не старый полноразмерный экспорт.
- Закреплённую версию фреймворка и исходные URL/revision, если доступна, сохранять
  в provenance. GrandTour сейчас скачивает HF без `revision`: не обещать pin данных
  только из-за pin submodule; не вводить обход этого вызова или второй загрузчик.

## BotanicGarden как новый адаптер

Уточнение от 2026-10-13: подготовка BotanicGarden уже реализована в
`scripts/prepare.py::botanicgarden` и вызывается через `make prepare`/`make convert`.
Она извлекает камеры и raw Xsens IMU с timestamps из `header.stamp`, записывает
калибровку и читает corrected `/gt_poses` из отдельного GT bag. Текущий результат —
EuRoC-подобный `mav0/...` и `reference/poses.tum`; GT остаётся в frame VLP16,
а `T_imu_reference` сохраняется отдельно в metadata.

Задача переезда — перенести проверенную логику существующего конвертера в hooks
штатного адаптера, используя общие ROS1-утилиты, и заменить выход на
`rgb_0/`, `rgb_1/`, `rgb.csv`, `imu_0.csv`, `calibration.yaml`, `groundtruth.csv`.
GT при этом приводится к body frame Xsens. Отсутствует именно адаптер внутри
VSLAM-LAB, а не конвертация исходных данных вообще. Скачанные VLIO bags и corrected
GT подходят для нового импорта; повторная загрузка в другом формате не нужна.

Основа — [официальный гайд интеграции](https://github.com/VSLAM-LAB/VSLAM-LAB/wiki/Integrate-a-new-VSLAM-Dataset):
класс датасета, YAML, регистрация в `Datasets/get_dataset.py`, стандартный layout,
проверка через `pixi run validate-dataset botanicgarden`.
Примеры wiki содержат старые имена/сигнатуры; точный API брать из закреплённой
ревизии `7595da8e516ec8b7e3194d1b9fa9dc01718b513c`, её `DatasetVSLAMLAB`,
`dataset_template.py/.yaml` и `dataset_hilti2022.py`.

### Регистрация и поставка кода

- Добавить в VSLAM-LAB `Datasets/dataset_files/dataset_botanicgarden.py`:
  класс `BotanicgardenDataset(DatasetVSLAMLAB)`.
- Добавить `dataset_botanicgarden.yaml` и ключ `botanicgarden` в `get_dataset`.
- YAML: `rgb_hz: 10.0`, `modes: [mono, mono-vi, stereo, stereo-vi]`,
  `cam_models: [radtan4]`, `raw_formats: [ros1, zip]`.
  Начальные последовательности: `1018_00`, `1018_13`.
- Первой проверять/включать `1018_00`, затем `1018_13`; обе выбраны для загрузки
  с SJTU вместе с corrected GT. Их VLIO bags — примерно 5,83 и 9,45 GB соответственно.
  Уже скачанные файлы переиспользовать после проверки manifest/checksums.
  `1005_00` оставить дополнительным кандидатом вне начального набора.
- Код адаптера и необходимые общие исправления вести в fork `dyepine/VSLAM-LAB`
  обычными Git-коммитами. Submodule закреплён на конкретном опубликованном commit;
  bootstrap получает код через штатный `git submodule update --init`.
  Чистый checkout проверяется тестами. При обновлении framework проверить
  совместимость адаптера перед сменой pin. Авторство, лицензия и metadata — по шаблону.

### Что делают hooks

| Hook | Ответственность |
|---|---|
| `download_sequence_data` | Официальные OneDrive VLIO bag и corrected `gt_<sequence>_qnew.bag`, calibration из закреплённой версии BotanicGarden; проверить размеры/checksums |
| `create_rgb_folder` | Извлечь `/dalsa_gray/left/image_raw` и `/dalsa_gray/right/image_raw` в `rgb_0`/`rgb_1` через общие ROS1-утилиты |
| `create_rgb_csv` | Использовать timestamps каждой камеры из `header.stamp`, сопоставить по времени, явно учесть пропуски; не соединять камеры по номеру строки |
| `create_imu_csv` | Извлечь raw Xsens `/imu/data` в стандартный `imu_0.csv`, ns, rad/s и m/s²; время из `header.stamp` |
| `create_calibration_yaml` | Официальные intrinsics/distortion и extrinsics в body frame Xsens; записать через `write_calibration_yaml` |
| `create_groundtruth_csv` | Corrected `/gt_poses` из отдельного GT bag, преобразовать pose VLP16 в body frame Xsens, записать стандартные 8 колонок |
| `remove_unused_files` | Соблюдать retention; не удалять оригинальные bags/GT/calibration при миграции |

Сначала оставить официальный опубликованный image stream 960×600, 10 Hz без
дополнительного resize (`target_resolution` не задавать). Полные 1920×1200/40 Hz
из sensor specifications не подставлять вместо параметров выбранного VLIO bag.
Если позднее нужен resize, применять общие `compute_scaled_size` и
`scale_intrinsics`, фиксируя его как изменение входных данных эксперимента.

### Переиспользование вместо второго экспортера

Локальная проверка скачанного `1018_00_VLIO.bag` от 2026-10-13:
размер и MD5 совпали с manifest; по 964 кадра gray-камер 960×600,
camera span около 96 с при bag span около 148 с. Предпросмотр:
[кадры и описание](../results/botanicgarden-1018-00-preview-20261013/README.md).
В ROS1 index headers меняется порядок полей; установленный `rosbags` кеширует
первый порядок и падает при чтении. При приёмке общего extractor проверить
совместимость с этим реальным bag, не обходить проверки длины/целостности.
Corrected `/gt_poses` в этом VLIO bag отсутствует: отдельный GT по-прежнему нужен.

- Использовать существующий Pixi `ros1`, `run_rosbag_frame_extraction` и
  `extract-rosbag-imu`. Не заводить отдельный `.venv` для подготовки BotanicGarden.
- В текущем frame extractor обнаружены bag receive time (`t`) и index join камер;
  ошибки декодирования пропускаются. До применения добавить небольшие совместимые
  опции общих утилит: строгий `header.stamp` и остановку при ошибках extraction.
  Для BotanicGarden `create_rgb_csv` должен строить окончательные пары по
  независимым timestamps; промежуточный index join не является готовым stereo CSV.
  Точность/tolerance pairing определить по исходным stamps и документированной
  синхронизации, не переносить автоматически 2 ms из GrandTour.
- Corrected GT bag читать в том же `ros1` environment; при необходимости добавить
  небольшой общий reader pose messages. Перенести только BotanicGarden parsing и
  проверенную transform-логику из `prepare.py`, не весь старый pipeline и layout.
- Использовать общий `downloadFile`, адаптируя точное имя файла и проверку checksum
  в адаптере. SJTU URL заканчивается `/content`: не допускать конфликтов имён и
  считать скачивание завершённым только после проверки содержимого. Общие GT/calib
  файлы хранить один раз на датасет, не копировать для каждой последовательности.
- Не держать скрытое состояние между hooks: каждый получает нужное по
  `sequence_name` и файлам. Повторный импорт должен распознавать незавершённый
  результат и возобновляться без удаления пользовательских данных.

### Калибровка и GT

Body frame — Xsens. `T_BS` переводит координаты сенсора S в B; для IMU — identity.
Сохранить композицию `T_xsens_gray0 @ T_gray0_gray1` и сверить её с исходной
калибровкой/тестами; независимую gray1/Xsens-калибровку сохранить как source.
При записи IMU noise проверить смысл и единицы официальных Xsens-параметров
против полей VSLAM-LAB, не придумывать отсутствующие коэффициенты или priors.

В старом exporter GT сохраняется в frame VLP16; теперь `groundtruth.csv` должен
относиться к Xsens, как камеры/IMU:

```text
T_world_xsens = T_world_vlp16 @ inverse(T_xsens_vlp16)
```

Перед реальной оценкой подтвердить направление исходного transform и семантику
corrected GT. Сохранить исходную reference и metadata с преобразованием, оставить
world sequence-local. Не использовать старый GT из VLIO bag вместо corrected GT,
не изобретать covariance и не выдавать VIO-assisted reference за независимый.

## Порядок реализации и удаления

1. Перенести machine path из `StorageConfig`, унифицировать выбор записей;
   сделать `make prepare` для штатного GrandTour. Проверить на KÄB-1, затем ALB-1.
2. Добавить BotanicGarden adapter и необходимые совместимые ROS1 helper changes.
   Проверить hooks на синтетическом bag с отличающимися header/receive stamps,
   пропущенным кадром и известными transforms; затем на реальной `1018_00`.
3. После проверки стандартного BotanicGarden layout убрать старый `prepare.py`,
   GrandTour/BotanicGarden записи старого `datasets.json`, storage/selection YAML
   старого pipeline, устаревшие Make targets и тесты EuRoC-like output.
   Проверки BotanicGarden перенести в тесты нового адаптера, не потерять их.
4. Проверить потребителей requirements: удалить `zarr`/`numcodecs`/`rosbags` и
   прочие зависимости только если они больше не нужны. Не затронуть evo/viewer.
5. Обновить README/help/PLAN и pin submodule после доступности нового commit.
   Старые raw/processed, архивы, логи и результаты сохраняются; удаление кода
   не является разрешением удалить большие файлы данных.

## Приёмка переезда

- Чистый checkout + submodules имеет адаптер и нужные environment dependencies;
  импорт не требует копирования кода вручную. `validate-dataset` проверяет адаптер,
  но не заменяет проверку содержимого реальных записей.
- `make prepare` и `make run` выбирают одинаковые dataset/sequence и путь.
- Повторная подготовка не перезаписывает готовые данные; прерванный импорт
  восстанавливается или выдаёт конкретную ошибку с безопасным способом продолжения.
- CSV конечны и timestamps возрастают; изображения существуют, calibration
  соответствует их размеру; stereo пары по времени и общий camera/IMU interval
  проверены, пропуски видны в отчёте.
- Для выбранных GrandTour-записей GT получен из `cpt7_ie_tc_odometry`, источник
  записан в provenance/отчёте; проверка по призме для приёмки не требуется.
  GT приведён в тот же body frame, quaternion валидны; position-only prism fallback
  не принимается как полноценный 6DoF GT для выбранных основных GrandTour-записей.
- Аудит команды ORB-SLAM3 подтверждает реальные входы и включительные границы
  `rgb_idx`; короткий реальный прогон выполняется только на стабильном носителе.
- Оценка и визуализация читают стандартные outputs, сохраняют SE(3) без scale
  correction и ограничения GT. Успешный импорт не доказывает успешность VIO.

Оценку пиковой потребности в диске пересчитать под стандартную распаковку и
retention: старый `make plan` считает другой формат. Сохранить проверку свободного
места до больших загрузок; не переносить его числа как готовую гарантию.
Проблема стабильности T7 из `PLAN.md` остаётся отдельным условием реальных прогонов.

## Первичные источники и исходники

- [Гайд VSLAM-LAB](https://github.com/VSLAM-LAB/VSLAM-LAB/wiki/Integrate-a-new-VSLAM-Dataset)
- [BotanicGarden: поставка, сенсоры и синхронизация](https://github.com/robot-pesg/BotanicGarden)
- `external/VSLAM-LAB/Datasets/DatasetVSLAMLAB.py`
- `external/VSLAM-LAB/Datasets/extra-files/dataset_template.py` и `.yaml`
- `external/VSLAM-LAB/Datasets/dataset_files/dataset_grandtour.py`
- `external/VSLAM-LAB/Datasets/extra-files/extract_rosbag_frames.py` и `extract_rosbag_imu.py`
- `scripts/prepare.py` из истории Git: исходная BotanicGarden parsing/calibration/reference
  логика перенесена в адаптер; legacy exporter удалён.

## Ход реализации — 2026-10-13

- Подготовка и runner используют `dataset_inputs.py`: общий experiment Config и
  `${VIO_DATA_DIR}`. `StorageConfig` удалён из experiment, make вызывает штатный
  lifecycle; отдельные download/convert targets удалены.
- Зарегистрирован BotanicGarden adapter с сохранением исходников, строгим ROS1
  header-stamp extraction, stereo pairing и преобразованием GT VLP16 -> Xsens.
- Native ROS1 reader в Pixi прочитал реальную 1018_00 без ошибки порядка index
  headers; обход установленного rosbags больше не требуется для подготовки.
- Проверены 964 пары с одинаковыми timestamps, 46081 IMU, 1300 валидных GT poses.
  В corrected GT одна исходная quaternion NaN (timestamp 1666059896607057000):
  исходный CSV сохранён, поза исключена из рабочего GT и отмечена в metadata.
- Исходная rotation T_xsens_vlp16 имеет ортогональность с ошибкой около 1.76e-6;
  проверка допускает 1e-5 для опубликованной точности записи, грубые не-rotation
  matrices отклоняются.
- Каталог данных переключён в локальной `.envrc` на T7:
  `/media/napalkov/T7/vio_research/data`. Проверенная BotanicGarden скопирована
  туда с сохранением внутренней копии; `make validate` на T7 прошла.
  Проверка 1 MiB write/fsync/read прошла; после переподключения 12 октября
  в 20:47 новых USB/exFAT ошибок в журнале не найдено. Это не гарантирует
  стабильность длительной нагрузки.
- Для KÄB-1 estimate дополнительных данных около 32.89 GB; на T7 preflight
  проходит. Запущена последовательная штатная подготовка KÄB-1, затем ALB-1.
  Реальная приёмка этих записей остаётся впереди до завершения процесса.
- Старый exporter, manifest, selection/storage YAML и их offline-тесты пока
  сохранены до приёмки GrandTour. Legacy CLI не является текущим make workflow.
- Commit/публикация framework branch и обновление submodule pin остаются впереди;
  локальный provenance явно записывает dirty framework. Чистый checkout пока
  не воспроизводит новый BotanicGarden adapter.

- Сквозной smoke-test ORB-SLAM3 stereo-VI на BotanicGarden 1018_00 прошёл:
  exit code 0, 130.08 s, около 0.90 GB RAM; входы брались с внутренней
  сохранённой копии. Runner выбрал включительный rgb_idx [0,963], 964 кадра.
  Native trajectory прочитана нашим evaluator с исходным SE(3) протоколом.
  Результаты: `results/botanicgarden-smoke/2026-10-13_02-43-08/`.
- Проверки: 9 новых migration-тестов (включая реальный synthetic ROS1 bag,
  пропущенный right frame и HTTP Range), 31 прежний offline-тест,
  18 evaluator-тестов. Framework validator также проверяет новый адаптер;
  поддержка его собственной HTML README table исправлена в общем validator.

- Runner переименован в `scripts/run_vio.py`: имя больше не привязано к ALB-2;
  основной поддерживаемый вход остаётся `make run`.

- Для BotanicGarden smoke-оценки при прежнем допуске association 10 ms совпали
  52 из 252 сохранённых поз (20.63%). Редкий GT требует отдельного решения о
  временном сопоставлении; tolerance и временной сдвиг не подгонялись автоматически.

- KÄB-1 импортирована на T7 штатным адаптером: 4790 stereo-пар, 95809 IMU,
  96001 GNSS/INS poses; для VIO 4788 пар, первые две исключены по IMU bracketing.
  ALB-1 готовится следующим шагом фонового процесса.
- Для короткой проверки добавлен `grandtour_kaeb_1_smoke.yaml` с штатным
  `Parameters.rgb_max: 200`. Framework применяет cap; runner проверяет фактический
  CSV и записывает использованное число кадров. `CONFIG` работает одинаково
  для `make prepare` и `make run`.

- Короткий ORB-SLAM3 smoke на KÄB-1 с T7 также завершился с exit code 0:
  200 кадров, около 60 s wall time и 0.34 GB RAM. Результат сохранён в
  `results/grandtour-alb2/2026-10-13_02-53-14/` (старый локальный results root;
  последующие запуски по умолчанию идут в `results/vio`).

- ALB-1 также подготовлена на T7: 2957 stereo-пар, 59138 IMU и 59201
  GNSS/INS poses; первые две пары исключены по IMU bracketing.
- После приёмки удалены `scripts/prepare.py`, `configs/datasets/datasets.json`,
  `configs/datasets/prepare.yaml`, `tests/test_prepare.py`. Нужные проверки
  представлены migration-тестами; legacy output-тесты больше не нужны.
  Bootstrap requirements сокращены до numpy/PyYAML; Pixi/ROS1 и окружение
  evo/viewer сохранены. Установленные пакеты и все исходные данные сохранены.
- Загрузка BotanicGarden 1018_13 остаётся незавершённой: SJTU обрывает ответы.
  `.part` сохранён; adapter блокирует повторную параллельную загрузку при
  наличии незавершённого файла в явно выбранном local source directory.

- Финальные проверки после удаления legacy: `make test` — 47 тестов
  (9 migration + 20 environment/input/result + 18 evaluator), все прошли.
  `make validate` для BotanicGarden 1018_00, KÄB-1 и ALB-1 на T7 прошёл,
  включая проверку размерности всех изображений. Новых USB/exFAT ошибок
  во время подготовки в журнале не обнаружено.
- Smoke-оценка KÄB-1 сопоставила все 29 сохранённых поз с GNSS/INS GT.
- SJTU `1018_13` endpoint действительно игнорирует HTTP Range: запрос с
  offset 4718592 вернул HTTP 200 без Content-Range и начало ROS bag.
  Frontend `?download=1` ведёт себя так же. Докачка этим источником в текущем
  тесте не поддерживается; серия оборванных полных ответов не завершила загрузку.
  Это ограничение источника, а не успешный импорт 1018_13.
- Для публикации и смены pin запрошен URL GitHub fork; до его согласования
  изменения submodule остаются локальными и не выдаются за воспроизводимый pin.


## Уточнение цели и реализация — 2026-10-13, 03:20 MSK

Этот раздел заменяет прежнее требование получить URL fork до воспроизводимой
поставки адаптера. Текущая поставка — upstream submodule с прежним точным pin
и версионируемый `patches/vslamlab.patch`, применяемый стандартным `git apply`.
По последующему решению пользователя патч остаётся основным способом поставки;
fork/upstream-публикация не планируется. Изменения пока находятся в working tree;
commit/push в этой задаче не выполнялись.

- `make prepare` устанавливает локальный Pixi, инициализирует submodule,
  устанавливает frozen VSLAM-LAB/ROS1 окружения и готовит четыре записи из
  `configs/datasets/selected.yaml`. Переопределение `CONFIG` сохраняется.
- `make run METHOD=... MODE=...` формирует уникальный native experiment и
  вызывает штатные `run_exp`/`run_sequence`. Установка метода, weights,
  calibration conversion, frame filtering, выполнение и logs принадлежат VSLAM-LAB.
  `verbose=0` выключает viewer; первая попытка KÄB-1 с native default
  `verbose=1` завершилась segfault, повтор с 0 прошёл.
- Для штатных commands добавлены environment overrides benchmark/evaluation
  paths. Данные на T7 доступны и pipeline, и dataset adapters.
- Прежний no-loop/provenance/SE(3) путь остаётся в `make run-research`;
  custom Evaluation/MethodSettings не применяются к catalog-run. Native
  Sim(3)-оценка автоматически не включается, метрики не смешиваются.
- GrandTour теперь возобновляет начатую им конвертацию после прерывания:
  pending marker охватывает весь lifecycle, camera completion markers
  отличают полную конвертацию от частичной папки. Нет удаления пользовательских данных.
- BotanicGarden регистрирует начатый импорт до network IO и докачивает явно
  выбранный local `.part` на месте. Прежнее требование вручную докачать его
  перед запуском adapter отменено.

Проверено:

- 51 тест: 11 migration + 22 environment/bootstrap/input/result + 18 evaluator.
- Patch delivery и идемпотентный повтор на чистом checkout upstream; конфликтующие
  изменения не сбрасываются. Это проверка поставки, не полный прогон на свежей ОС.
- Настоящая загрузка нового Pixi binary из official release, SHA-256 и frozen install.
- Native ORB-SLAM3 stereo-VI: KÄB-1 и BotanicGarden 1018_00, по 200 кадров, SUCCESS=True.
- Native ORB-SLAM2 stereo: BotanicGarden 1018_00, 200 кадров, SUCCESS=True;
  метод и vocabulary установлены автоматически framework средствами.
- Prepared sequence/GT checks для KÄB-1, ALB-1 и BotanicGarden 1018_00 ранее прошли.

Полная приёмка четырёх записей ещё не завершена: SJTU 1018_13 неоднократно
обрывает full response и не поддерживает Range на проверенных endpoints.
Загрузка запущена через `make prepare CONFIG=...1018_13_orbslam3.yaml`;
log: `results/botanicgarden-download-20261013/prepare-13-native.log`.
Загрузчик автоматически повторяет попытки, проверяет полный размер и MD5
и только затем продолжает импорт. Импорт 1018_13 пока не подтверждён.


## Поставка через fork — окончательное решение 2026-10-13

Пользователь пересмотрел решение о патче и разрешил перейти на fork/submodule.
Этот раздел заменяет предыдущие решения о способе поставки.

- Fork: https://github.com/dyepine/VSLAM-LAB, default branch `vio-research-datasets`.
- Upstream остаётся https://github.com/VSLAM-LAB/VSLAM-LAB; PR туда не создавался.
- `c523bb7`: strict ROS helpers, named verified downloads, optional IMU fields,
  environment paths, recovery interrupted GrandTour conversion и validator.
- `6a865b197e7d3fa5d952412bc1905159e3cbaabe`: BotanicGarden adapter,
  registration, native test configs и metadata. Это закреплённый gitlink.
- `.gitmodules` указывает на fork. Bootstrap читает pin из Git index и использует
  штатный `git submodule update --init`; дополнительных патчей/копирования нет.
- `patches/vslamlab.patch`, сопроводительный README и применение патча удалены
  после проверки свежего клона с GitHub: все 14 файлов совпали, checkout чистый.
- 51 тест прошёл до и после перехода. Bootstrap regression tests проверяют
  чистый checkout, повторный запуск и отказ при чужой ревизии без сброса данных.

Способ поставки не меняет форматы, методы и оценку. Полный импорт BotanicGarden
1018_13 остаётся отдельным незавершённым пунктом, связанным с доступностью зеркала.


## Устойчивость к обрывам — 2026-10-13

Текущий submodule pin: `eb34016b0f6ac494ca42d2a65ce81307c17244b0`.

- Проверенные SJTU API/frontend endpoints игнорируют Range и возвращают HTTP 200
  с начала файла. Поэтому увеличение количества полных повторов не решает докачку.
- Bag source metadata теперь содержит официальные OneDrive share links из README
  авторов. После обрыва/отказа Range адаптер переключается с SJTU на OneDrive.
- Разрешение public share использует протокол `eugenenuke/onedrive-downloader`;
  передача байтов остаётся в общем downloader VSLAM-LAB. Новых зависимостей нет.
  Подписанные URLs и anonymous tokens не сохраняются и не выводятся.
- При каждой попытке проверяются имя и размер source, URL обновляется. При
  докачке проверяются начало Content-Range и полная длина файла. `read1` сохраняет
  все полученные байты даже при обрыве до очередного блока в 1 MiB.
- Лимит ошибок учитывает только попытки без прироста сохранённых данных;
  продвигающиеся загрузки могут пережить любое число обрывов. `.part` не
  обнуляется на отказе Range, размер и MD5 проверяются перед final rename.
- При наличии разных partial в Downloads и на SSD выбирается больший;
  старый partial сохраняется. Реальный источник фиксируется в sources.json.

Реальная проверка: OneDrive 1018_13 отвечает HTTP 206 на диапазон
1048576–1048639 с полной длиной 9453894870. Загрузка продолжила сохранённые
86216243 bytes на T7; после принудительного SIGINT на 332561971 bytes
повторная команда продолжила с этого смещения. После повтора файл вырос
до 792358451 bytes. Полный MD5/import 1018_13 ещё не подтверждён.
Synthetic transfer пережил 25 принудительных обрывов; recovery/source/checksum
и Git delivery входят в regression tests. Logs:
`results/botanicgarden-download-20261013/prepare-13-resumable*.log`.


## OneDrive основной источник — 2026-10-13

По запросу пользователя SJTU исключён из новой сетевой подготовки BotanicGarden.
Submodule pin: `1a8a33a32a036076da24e7dd6e305df446226562`.

VLIO bags и corrected GT bags для обеих выбранных записей скачиваются сразу
с официальных OneDrive share links. GT bags получают отдельные size/MD5,
сверенные с прежним проверенным GT_pose_qnew.zip. Старые ZIP imports остаются
читаемыми, новые не требуют ZIP или SJTU. Calibration по-прежнему pinned GitHub.

Проверка настоящего OneDrive transfer на GT 1018_13: после получения 1622 bytes
чтение принудительно оборвано ConnectionResetError. URL обновлён, сервер вернул
HTTP 206 Content-Range bytes 1622-276790/276791; загрузка завершилась с ожидаемым
MD5 d64f15d54afdbfc972414947b068185a. Также полностью проверен GT 1018_00:
188248 bytes, MD5 ed0e99e2696574a8c4b8a6ae1616d0d4. Новый direct-GT hook
проверен реальным ROS1 reader и преобразованием в Xsens frame: 1938 поз для 13.

В текущей большой загрузке естественных OneDrive обрывов в наблюдавшемся log
не было. Это не доказательство их отсутствия в будущем; проверена именно
обработка обрыва и докачка. Активный 1018_13 transfer уже идёт с OneDrive и
не перезапускается ради изменения выбора источника. Full bag MD5/import ожидается.
Evidence: results/onedrive-resume-check/verification.json.


## Прогресс загрузки — 2026-10-13

Submodule pin: `6657e8ccd1c3ac166375bffe1581610cf8c4eb68`. Общий verified downloader использует уже
установленный tqdm: terminal bar показывает процент, байты, скорость и ETA,
initial соответствует фактическому .part после принятия HTTP Range. Проверка
полного checksum тоже имеет progress bar. В non-TTY динамический вывод отключён.
PTY smoke download начался с 24% сохранённых байтов и завершился с правильным MD5;
transfer recovery и checksum contracts проверяются существующим regression suite.


## Каталог всех публичных записей — 2026-10-13

Submodule pin: `219df9d6667817db42e7b7a1db902fc7825807ea`. В dataset_botanicgarden.yaml перечислены
все 10 публичных последовательностей из двух таблиц README авторов. Проверены
20 public OneDrive share metadata: ожидаемые имена и размеры bags/GT. MD5
семи основных bags сверены по опубликованному файловому каталогу, GT MD5 —
по целиком полученным небольшим corrected bags (семь также совпали с прежним ZIP).
Для bags 1005_05, 1006_03, 1008_01 закреплены SHA-256 из OneDrive metadata;
полные большие bags этих записей не скачивались и imports не проверены.

Наш configs/datasets/selected.yaml по-прежнему выбирает только 1018_00/1018_13;
каталог определяет доступность, selection — что скачивать. Storage preflight
использует опубликованные durations и native 10 Hz с явным planning margin,
а не таблицу только двух последовательностей. Остальные 23 записи доступны
у авторов по запросу и не снабжаются выдуманными URL.

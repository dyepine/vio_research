# Датасеты и соглашения координат

Выбор для отчёта — `configs/datasets/selected.yaml`: GrandTour `kaeb_1`,
BotanicGarden `1018_13`, GEODE `offroad1`. Он совпадает с `Datasets` обеих
активных матриц. Команды подготовки и системные зависимости — в [README](../README.md).

Подготовленные записи имеют формат VSLAM-LAB:

```text
${VIO_DATA_DIR}/VSLAM-LAB-Benchmark/<DATASET>/<sequence>/
  rgb_0/, rgb_1/
  rgb.csv
  imu_0.csv
  calibration.yaml
  groundtruth.csv
  preparation_report.json
```

`T_A_B` переводит координаты из B в A. `T_BS` в калибровке задаёт позу
сенсора в корпусе; она не обязана быть identity. Timestamps сохраняются
как int64 ns, кватернионы CSV — xyzw. Калибровка и reference преобразуются
к body каждой записи; адаптеры методов экспортируют body либо явно указанную
камерную позу. Правила оценки — в [README](../README.md).

## GrandTour

Используется адаптер `grandtour-alphasense`: стереопара global-shutter камер,
BMI085, изображения 640×480. Для `kaeb_1` нужен GNSS/INS reference
`cpt7_ie_tc_odometry`, приведённый в систему Alphasense IMU.
Prism-only fallback не принимается как полноценный 6DoF GT.
HF revision исходных данных штатным адаптером не закрепляется;
это ограничение записывается в provenance подготовки.

Профиль IMU в эксперименте — опубликованные white-noise densities и
исторические random walks `sigma_gw_c=0.000266`, `sigma_aw_c=0.0043`.
Он общий для всех методов. A/B по random walks проводился только для ORB-SLAM3;
его результат не доказывает оптимальность профиля для остальных методов.
Точные значения находятся в YAML эксперимента, эффективные — в
`calibration_exp.yaml` каждого запуска.

## BotanicGarden

Используются VLIO bag и corrected `gt_1018_13_qnew.bag` с OneDrive,
проверяемые по опубликованным MD5, и калибровка из закреплённой Git-ревизии.
Серая стереопара — 960×600, nominal 10 Hz; Xsens IMU — nominal 400 Hz.
Извлечение использует `header.stamp`, пары камер имеют одинаковое время.

Body — Xsens. Corrected GT VLP16 преобразуется по формуле:

```text
T_world_xsens = T_world_vlp16 @ inverse(T_xsens_vlp16)
```

Исходный GT сохраняется в `groundtruth_vlp16.csv`. Нечисловые позы
исключаются без интерполяции, их timestamps записываются в
`reference_metadata.json`. Reference использует VIO-assisted tracking
и не является полностью независимым от визуального метода.
Общий профиль IMU в эксперименте — рабочие настройки авторов ORB-SLAM3,
а не утверждение о независимо измеренном шуме Xsens.

Исходники сохраняются. `BOTANICGARDEN_SOURCE_DIR` позволяет переиспользовать
скачанные bags; прерванный импорт возобновляется, неизвестные частичные
каталоги не перезаписываются.

## GEODE

Адаптер — `Datasets/dataset_files/dataset_geode.py` в submodule,
имя каталога `geode-gamma`. В отчёте используется ректифицированная Offroad1 γ:
1224×1024, nominal 10 Hz, внешний Xsens MTi-30 `/imu/data`, nominal 100 Hz.
IMU `/livox/imu` не используется. Камеры читаются из
`/left_camera/image/compressed` и `/right_camera/image/compressed`.
Пары ближайших timestamps сопоставляются с допуском 2 ms без повторного
использования правого кадра. Этот допуск не является измерением аппаратной синхронизации.

Bag проверяется по размеру и Drive MD5, calibration и reference — по SHA-256
из адаптера. Используется именно Drive calibration: версия в GitHub отличается.
`GEODE_SOURCE_DIR` позволяет переиспользовать исходники; незавершённые скачивания
сохраняются как `.part`. Сырые файлы остаются в `GEODE-GAMMA/raw`.

### Калибровка

Все пять коэффициентов исходной radtan5 участвуют в ректификации.
Выход описывается pinhole-геометрией с четырьмя нулевыми коэффициентами
для совместимости с reader ORB-SLAM3. Используется цепочка из двух
camera–IMU transforms, а не отдельная stereo calibration: эти источники
расходятся примерно на 5.56 mm / 0.69°. База выбранной цепочки — около 0.19354 m.
Проверки эпиполярной геометрии поддерживают этот выбор, но не подтверждают
независимо точность внешней калибровки.

Body адаптера — опубликованная beta reference frame. Межустановочное
преобразование взято из авторского
[gamma2GT_gnss.py на закреплённой ревизии](https://github.com/PengYu-Team/GEODE_dataset/blob/c6e930623d4fed450d7fc50e16e3ffe0288b692b/script/gamma2GT_gnss.py):

```text
T_world_beta = T_world_gamma_lidar @ inverse(T_beta_gamma_lidar)
T_beta_imu = T_beta_gamma_lidar @ inverse(T_IMU_LiDAR)
T_imu_left = T_IMU_CamL
T_imu_right = T_IMU_CamR
T_right_left = inverse(T_imu_right) @ T_imu_left
T_beta_rect_camera = T_beta_imu @ T_imu_camera @ T_camera_rect_camera
```

Калибровочные цепочки, версия ректификации и версия OpenCV записываются
в `calibration_metadata.json` и `rectification.json`. Калибровка создаётся
из фактического результата извлечения. Подготовка rectification-v1 сохраняется
резервной копией перед переходом на camera–IMU цепочку версии 2;
исторические результаты автоматически не переоцениваются.

### Reference и ограничения

GT — опубликованный GNSS/INS-RTK `Offroad1.txt`. В исходнике 42 626 поз
и 880 соседних инверсий времени. Стабильная сортировка сохраняет исходные
timestamps; она не доказывает, что времена reference верны.
Повторные timestamps, нечисловые позы и неверные кватернионы отклоняются.

Позиции переносятся в локальное начало: `p_local = p_source - p_first`,
где первая поза выбирается по времени во всём GT. Масштаб и оси сохраняются.
Ориентации исходного TXT отдельно приводятся по принятому соглашению:

```text
R_new = Rz(90°) @ Rx(180°) @ R_source @ Rx(180°)
```

Позиции при этой поправке не поворачиваются, fitted bias не применяется.
Формула, origin и `orientation_convention_version: 1` записываются в
`reference_metadata.json`. Повторная подготовка обновляет GT из исходного TXT
без повторного применения поправки; копии GT старых запусков сохраняются.

Исходное соглашение GNSS/INS и точность калибровки независимо не подтверждены.
**GEODE остаётся предварительным метрическим сравнением.** Источники принятой
поправки и оценки до/после сохранены в
[artifacts/report/geode_reference](../artifacts/report/geode_reference/).

Исходники: [сайт GEODE](https://thisparticle.github.io/geode/),
[код датасета](https://github.com/PengYu-Team/GEODE_dataset),
[bag](https://drive.google.com/file/d/1v70uMx5GcjSpvLxA0YsEN6_wX7zK7yHT/view),
[Drive calibration](https://drive.google.com/file/d/1GheigvWF1YTTw-2y4XrN4f-5i5wh2m4s/view),
[reference](https://drive.google.com/file/d/15sbhriCWbvfBloe8qJOJPhBsda9eD7Mg/view).
Конкретные размеры, checksums и правила импорта закреплены в исходниках адаптера.

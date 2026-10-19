# SchurVINS в VSLAM-LAB

Основной запуск сдачи — `configs/experiments/report.yaml`. Команды частных
исторических проверок ниже сначала восстанавливают удалённый конфиг из Git;
они сохранены для проверки происхождения результатов.

Источник: [bytedance/SchurVINS](https://github.com/bytedance/SchurVINS), ревизия
`d8ab6dff20860694d8d879d716d7fd6cb2c2530e`. Локальная интеграция запускает
авторский stereo-inertial фильтр, без Ceres backend и loop closure.
Исходный checkout сохраняет авторские лицензионные notices (GPL-3.0).

```bash
git show 57913a2:configs/experiments/geode_schurvins.yaml > /tmp/geode_schurvins.yaml
make run CONFIG=/tmp/geode_schurvins.yaml JOBS=1
make evaluate RUN_DIR=/absolute/path/to/comparison_directory EVAL_ARGS="--saved-protocol"
```

При отсутствии бинарника адаптер автоматически запускает последовательную
локальную сборку. Для пересборки после изменения адаптера или patches:

```bash
bash external/VSLAM-LAB/Baselines/extra-files/schurvins/build.sh
```

Системные зависимости: CMake, C++14 compiler, Eigen3, OpenCV, Boost
filesystem/system/thread, glog, yaml-cpp и OpenMP runtime. Скрипт не устанавливает
системные пакеты. Сборка использует `-O1 -DNDEBUG`, без upstream fast-math;
время обработки не следует считать воспроизведением авторского benchmark FPS.
Minkindr закреплён на `564f12639a8447d4d3e5e7707851424302941056`, FAST на
`4914ed963aba8d2bb476551e186e4b20a206f03d`, OpenGV на
`306a54e6c6b94e2048f820cdf77ef5281d4b48ad`.
В текущей проверке использована существующая статическая сборка OpenGV из
OKVIS1; предусмотренный путь сборки OpenGV с нуля отдельно не проверен.

ROS master, GUI и playback bag не нужны. Копия авторской factory генерируется
в build-каталоге; доступ к ROS parameters заменён чтением YAML. Калибровка и
профиль по-прежнему поступают в авторские классы. Runner подаёт упорядоченные
изображения и IMU, выставляет те же IMU rotation priors, что ROS interface,
и сохраняет текущую позу IMU. Асинхронный depth filter сохраняет авторское
поведение, поэтому побитовая воспроизводимость повторов не заявляется.

Профиль скопирован из upstream `svo_ros/param/vio_stereo.yaml`.
Нет оптимизации настроек по GT. Камеры получают K, D и
`T_imu_cam = inverse(T_BI) @ T_BC` из `calibration_exp.yaml`, шумы и gravity —
из той же материализованной калибровки. Поддержаны pinhole с radtan4/equid4;
radtan5 отвергается. Здесь используется ректифицированный `geode-gamma/offroad1`
1224×1024 с нулевой дисторсией. Начальные biases нулевые, как в авторском
профиле; готовая ориентация Xsens и ground truth в фильтр не поступают.

Timestamp читается как int64 nanoseconds; общий origin вычитается до
преобразования в double seconds. IMU перед каждым кадром подаётся до первого
измерения строго после обеих камер. Timestamp пары — левый, допустимое
расхождение с правым — менее 5 ms. Выход переводится в body датасета:
`T_WB = T_WI @ inverse(T_BI)`. Сохраняются обычный pose CSV VSLAM-LAB,
сырой IMU pose CSV, стадии трекинга и JSON provenance с ревизией, hash
бинарника, patches, калибровки, manifest и IMU.

## Изменения авторского кода

Оба изменения сохранены отдельными patches и применяются идемпотентно:

* `calibration.patch` передаёт gravity из IMU calibration в SchurVINS.
  Upstream фильтр иначе оставляет собственное жёсткое значение 9.81007,
  хотя IMU handler читает другое значение из YAML; GEODE задаёт 9.80665.
* `imu_timestep.patch` разбивает шаг propagation >=15 ms на шаги <=10 ms
  с тем же удерживаемым измерением, обновляя состояние и covariance на каждом
  шаге. Upstream завершал процесс через CHECK при dt >=15 ms. В исходном
  GEODE IMU CSV 40492 измерения, девять интервалов >=15 ms, максимум
  15.970468 ms; отрицательных и нулевых интервалов нет. Данные и их timestamps
  не меняются. Это адаптация численного интегрирования к интервалам Xsens,
  а не доказанное исправление точности самого фильтра.

## Проверки

```bash
external/VSLAM-LAB/.pixi/envs/vslamlab/bin/python -m unittest discover -s tests/migration -p test_schurvins.py -v
```

Четыре теста проверяют перенос intrinsics/noise/gravity, camera–IMU цепочку,
выходную body-позу при ненулевых вращении и lever arm, отказ от radtan5 и
запрет подмены SchurVINS на Ceres backend/loop closure.

Первый реальный smoke на 200 парах воспроизвёл CHECK с dt=15.6748 ms:
`comparison_20261019T162731_191745c8`. После timestep patch повтор
`comparison_20261019T163020_f2300de1` завершил все 200 пар и сохранил 200 поз.

## Полный GEODE Offroad1

Прогон `results/vio/VSLAM-LAB-Evaluation/comparison_20261019T163043_40cd6fe5`:
4048 входных пар → 4048 поз за 190.16 s; длительность записи 404.70 s.
Во всех строках native stage — `Tracking`, начальная инициализация одна.
Это не означает хорошую точность: траектория сильно разошлась, её длина
около 173.82 km. Причина разлёта этим прогоном не установлена.

Стандартный evo 1.34.3, сохранённый SE3-протокол **без коррекции масштаба**,
body frame, timestamp tolerance 0.05 s. Сопоставлены все 4048 поз с 4048
уникальными GT-позами; максимальное расхождение времени 8.33 ms.
RPE считается по GT-интервалам 1 m ±10%, 3685 пар.

| Метрика | RMSE |
| --- | ---: |
| APE position | 52154.81 m |
| RPE position | 1286.97 m |
| APE orientation | 138.26° |
| RPE orientation | 2.79° |

В каталоге сравнения сохранены `comparison.csv`, стандартные evo ZIP,
графики `figures/`, `schurvins_build_snapshot.json` с hashes сборки и адаптера,
`schurvins_run_audit.json` с полнотой выхода и стадиями. Детальные метрики:
`schurvins_stereo_vi_0/GEODE-GAMMA/offroad1/evaluations/00000/2026-10-19_19-34-24/summary.json`.
Логи smoke, полного запуска и оценки:
`results/vio/diagnostics/schurvins_geode_20261019/`.

Эта проверка подтверждает работоспособность интеграции и получение метрик;
профиль не обеспечивает устойчивую оценку на Offroad1. Выполнен один полный
прогон; статистика повторов, настройка под GEODE и чистая сборка всех
зависимостей не проверялись. Ограничения калибровки и GT — в [GEODE.md](GEODE.md).

## Другие локальные ROS1-записи

```bash
git show 57913a2:configs/experiments/ros1_schurvins.yaml > /tmp/ros1_schurvins.yaml
make run CONFIG=/tmp/ros1_schurvins.yaml JOBS=1
```

Матрица включает BotanicGarden `1018_00`, `1018_13` и GEODE `offroad7`.
Это запуск через файловый адаптер на уже извлечённых из ROS1 bag камерах/IMU;
ROS playback не используется. Авторский профиль фильтра и бинарник те же,
что в проверке Offroad1. Шумы BotanicGarden совпадают с существующими
сравнениями: gyro 0.002, accel 0.01, gyro walk 0.00008, accel walk 0.00003.
Оценка — body, SE3 без масштаба, dt 0.05 s, RPE 1 m ±10%.

Доступные stereo-интервалы: `1018_00` — 964 пары / 96.30 s,
`1018_13` — 1600 пар / 159.90 s, `offroad7` — 1839 пар / 183.80 s.
Из Offroad7 исключён один начальный кадр без IMU-окружения. В BotanicGarden
использованы все подготовленные кадры. Это не весь временной интервал bag
с другими сенсорами и GT: заявленные длительности записей больше.
Для `1018_00` исходный сенсорный bag сейчас отсутствует, сохранились
подготовленные данные и GT; `1018_13_VLIO.bag` и `Offroad7_gamma.bag` доступны.

Предварительный прогон по 200 парам каждой записи завершился:
`comparison_20261019T164157_6ad476bf`, 198/200/200 поз соответственно.

Полный batch: `comparison_20261019T164247_de96ebd8`. Все три процесса завершились,
по одному прогону записи; повторных инициализаций не было. Проверка ROS1 bag
`1018_13` подтвердила по 1600 сообщений каждой серой камеры и 73279 IMU:
подготовленный набор содержит весь стереопоток. Длительность самого sensor bag
182.15 s, длительность стереопотока 159.90 s. У Offroad7 bag содержит 1840 пар
и 18410 IMU, обработаны 1839 пар после проверки IMU-окружения.

| Запись | Входных пар | Поз | APE pos RMSE, m | RPE pos RMSE, m | APE rot RMSE, ° | RPE rot RMSE, ° |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| BotanicGarden 1018_00 | 964 | 962 | 17.7605 | 1.6007 | 10.9778 | 0.7899 |
| BotanicGarden 1018_13 | 1600 | 1600 | 1.9920 | 0.5537 | 1.1799 | 0.6579 |
| GEODE offroad7 | 1839 | 1839 | 6574.1268 | 180.7386 | 108.7269 | 4.8093 |

С GT сопоставлены соответственно 953, 1586, 1774 позы (99.06%, 99.13%, 96.47%
сохранённых поз); число уникальных GT-поз 952, 1586, 1774. Повтор одной GT-позы
в 1018_00 соответствует стандартной nearest-time association evo. Все метрики
доступны. Полное native-время первых двух запусков — 50.13 и 60.15 s.

На `1018_13` нет километрового разлёта; у `1018_00` заметно больше дрейф,
у `offroad7` сохраняется катастрофическое расхождение. В обоих BotanicGarden
native лог не содержит предупреждений `Not enough matched features`, у
Offroad7 их 1258. Эти наблюдения не устанавливают причину ошибок и не
проверяют исходный ROS interface SchurVINS независимо от файлового адаптера.
Один прогон не измеряет разброс результатов.

В каталоге batch: `comparison.csv`, `figures/`, обычные evo ZIP и summaries,
`schurvins_run_audit.json`, `schurvins_build_snapshot.json`, `ros1_inventory.json`.
Логи — `results/vio/diagnostics/schurvins_ros1_20261019/`.

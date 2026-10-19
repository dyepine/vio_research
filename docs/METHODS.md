# Методы и адаптеры

Основная матрица `report.yaml` запускает ORB-SLAM3, OKVIS1 и Voxel-SVIO.
`sqrtvins.yaml` добавляет отдельную проверку sqrtVINS на тех же записях,
с теми же профилями IMU и протоколом. Команды запуска и системные зависимости —
в [README](../README.md), происхождение входов — в [DATASETS.md](DATASETS.md).

## Общие соглашения

Все методы получают стереопару и IMU на проверенном camera–IMU интервале.
GT оценивателям не передаётся. Наносекунды сохраняются как int64;
при переводе во float секунды сначала вычитается общий origin.
Калибровка берётся из записи, шумы — из общего профиля эксперимента;
эффективные параметры сохраняются в `calibration_exp.yaml` и native YAML.

`T_BI` — поза IMU в body, `T_BC` — поза камеры в body.
Для IMU-позы экспортируется `T_WB = T_WI @ inverse(T_BI)`;
калибровка camera–IMU задаётся `T_IC = inverse(T_BI) @ T_BC`.
Камерный экспорт ORB-SLAM3 evaluator переводит по формуле
`T_WB = T_WC @ inverse(T_BC)`. Подгонка масштаба выключена.

Нативные адаптеры OKVIS1, Voxel-SVIO и sqrtVINS заменяют ROS-ввод/вывод
файловыми потоками. Python работает в Pixi, C++ использует системные библиотеки
Ubuntu 22.04. ROS master и playback не нужны. Детали сборки и патчи закреплены
в `external/VSLAM-LAB/Baselines/extra-files/`.

## ORB-SLAM3

Используется штатный baseline VSLAM-LAB `Module: orbslam3`, режим `stereo-vi`.
В основной матрице `Settings.loopClosing: 0`, viewer выключен.
Экспорт — поза `rgb_0`, поэтому в Evaluation заданы `estimate_frame: camera`
и `camera: rgb_0`. Оцениваются сохранённые ключевые кадры;
их timestamps отличаются от плотных выходов остальных методов.

Установка baseline и vocabulary выполняется lifecycle VSLAM-LAB.
Версии пакетов фиксируются Pixi lock; конфиг запуска и фактические параметры
сохраняются вместе с результатом.

## OKVIS1

[Авторский OKVIS 1.1.3](https://github.com/ethz-asl/okvis/tree/33ac70b4d95df98cd662086dc897b90a6f35d5a9)
закреплён на `33ac70b4d95df98cd662086dc897b90a6f35d5a9`.
Baseline — `Module: okvis1`, экспортируется body-поза.

`modernise.patch` адаптирует сборку к C++14 и Ceres 2.0; Ceres 2.2+ не поддерживается.
BRISK и OpenGV загружаются с проверкой SHA-256. IMU подаётся с запасом 30 ms
относительно камер; перед выходом ожидается последняя оптимизация.
Экспортируются реальные оптимизированные позы без интерполяции.

Поддерживаются pinhole, equid4, radtan4, radtan8. Radtan5 точно представляется
как `[k1,k2,p1,p2,k3,0,0,0]` в рациональной radtan8-модели; k3 не отбрасывается.
`imageDelay` должен быть нулём, timestamps должны быть уже откалиброваны.
Отсутствие визуальной инициализации считается ошибкой;
предупреждения трекинга сохраняются отдельно от статуса завершения процесса.

В результат входят `okvis1_native.yaml`, `okvis1_provenance.json`,
`okvis1_tracking.json`, timestamps изображений и стандартный trajectory CSV.
Субнормальные значения IMU читаются без изменения исходного CSV.

## Voxel-SVIO

[Авторская реализация](https://github.com/ZikangYuan/voxel_svio)
закреплена на `eac6b87d0f925b96ddd5c5c6b0dcda3d36c7ab5f`.
Baseline — `Module: voxel-svio`. JPL rotation `R_GtoI` переводится
в Hamilton-позу IMU, затем в body. Поддерживаются pinhole, equid4 и radtan4;
неподдерживаемые модели отвергаются явно.

В `Baselines/extra-files/voxel_svio/` находятся три патча:

- `offline.patch` — файловые входы/выходы и передача калиброванной gravity
  как initializer, так и propagator.
- `compatibility.patch` — определённый bool-return при заполненном voxel.
- `memory_safety.patch` — границы pixel selector для неполных блоков,
  определённые градиенты краевых строк обеих камер и обработка пустых блоков.

За основу взят авторский `config/euroc.yaml`; MLE initialization budget увеличен
с 0.05 до 5 s, число потоков — 2. Эти настройки не подбирались по GT.
PCL 1.12.1 headers распаковываются локально из пакета с SHA-256.
Экспорт выполняется после native state update. Сохраняются native YAML,
provenance, исходный `pose.txt` и body trajectory CSV; оценка использует CSV.

Native-тесты проверяют voxel, ориентацию и pixel-memory regression;
при наличии Valgrind Memcheck добавляется в CTest. Устранение ошибок памяти
не обеспечило устойчивого прохождения GEODE. В отчётной таблице `×` отражает
историю попыток; опорные числа сохранены в [наборе результатов](../artifacts/report/README.md).
Исторические измерения не приписываются бинарнику с более поздним memory fix.

## sqrtVINS

[Авторская реализация](https://github.com/rpng/sqrtVINS)
закреплена на `30fafc89d89cfb896d06fdaa68fbda8545e02e9f`.
Baseline — `Module: sqrtvins`, экспортируется body-поза. Код оценивателя
не менялся; используется float32, Release `-O1 -DNDEBUG` и последовательная сборка.

Профиль взят из `config/euroc_mav/estimator_config_srvins.yaml`:
фиксированная калибровка, нулевые начальные догадки bias, один поток OpenCV,
синхронная инициализация, `init_dyn_use: false`, без общих init-log файлов в `/tmp`.
Поддерживаются pinhole, radtan4 и equid4; radtan5 отвергается.
IMU подаётся до первого sample после обоих timestamps пары;
готовая ориентация Xsens и GT в оцениватель не поступают.
Сохраняется `sqrtvins_provenance_<iteration>.json` с хешами и ревизией.

В активном эксперименте окно инициализации — 2 s. Сохранённые проверки
GrandTour и GEODE находятся в
[additional/sqrtvins](../artifacts/report/additional/sqrtvins/): там есть summaries,
конфиги запуска и фактические native YAML. Контроль GrandTour с окном 0.15 s
разошёлся, с 2 s дал APE RMSE 1.052 м и RPE RMSE 0.024 м.
На GEODE сохранялось расхождение. Для BotanicGarden сохранённая оценка
sqrtVINS не найдена; новый конфиг для этой записи ещё не проверен.

## Пересборка

После изменения адаптеров или патчей существующий бинарник нужно пересобрать:

```bash
bash external/VSLAM-LAB/Baselines/extra-files/okvis1/build.sh
bash external/VSLAM-LAB/Baselines/extra-files/voxel_svio/build.sh
bash external/VSLAM-LAB/Baselines/extra-files/sqrtvins/build.sh
env -u LD_LIBRARY_PATH ctest --test-dir external/VSLAM-LAB/Baselines/Voxel-SVIO/build --output-on-failure
```

Исторические интеграции SchurVINS, PyCuVSLAM и DROID-SLAM не входят в отчётную
матрицу. Их адаптеры и тесты сохранены; документы до очистки доступны в Git
на коммите `90ce21f`, а частные конфиги — на `57913a2`.

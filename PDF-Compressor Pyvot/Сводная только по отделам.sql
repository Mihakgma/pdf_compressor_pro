-- Сводная только по отделам (регистронезависимая)
SELECT 
    CASE 
        WHEN LOWER(file_full_path) LIKE '%огдип%' THEN 'ОГДиП'
        WHEN LOWER(file_full_path) LIKE '%окг%' THEN 'ОКГ'
        WHEN LOWER(file_full_path) LIKE '%эо%' THEN 'ЭО'
        WHEN LOWER(file_full_path) LIKE '%огифт%' THEN 'ОГиФТ'
        WHEN LOWER(file_full_path) LIKE '%сгм%' THEN 'СГМ'
        WHEN LOWER(file_full_path) LIKE '%юр. отдел%' OR LOWER(file_full_path) LIKE '%юо%' THEN 'ЮО'
        WHEN LOWER(file_full_path) LIKE '%илц%' THEN 'ИЛЦ'
        WHEN LOWER(file_full_path) LIKE '%сго%' THEN 'СГО'
        WHEN LOWER(file_full_path) LIKE '%окс%' OR LOWER(file_full_path) LIKE '%конктракт%' THEN 'ОКС'
        WHEN LOWER(file_full_path) LIKE '%охоимтс%' THEN 'охоимтс'
        WHEN LOWER(file_full_path) LIKE '%оодц%' THEN 'ООДЦ'
        WHEN LOWER(file_full_path) LIKE '%бухгалтерия%' THEN 'бухгалтерия'
        WHEN LOWER(file_full_path) LIKE '%кадры%' OR LOWER(file_full_path) LIKE '%отдел кадров%' OR LOWER(file_full_path) LIKE '%ок%' THEN 'ОК'
        WHEN LOWER(file_full_path) LIKE '%администрация%' THEN 'администрация'
        ELSE 'Другое'
    END as "Отдел",
    COUNT(*) as "Количество файлов",
    ROUND(AVG(file_compression_kbites / 1024.0), 3) as "Средний объем сжатия, МБ",
    ROUND(SUM(file_compression_kbites / 1024.0), 3) as "Суммарный объем сжатия, МБ",
    ROUND(MIN(file_compression_kbites / 1024.0), 3) as "Минимальный объем сжатия, МБ",
    ROUND(MAX(file_compression_kbites / 1024.0), 3) as "Максимальный объем сжатия, МБ"
FROM processed_files
GROUP BY 
    CASE 
        WHEN LOWER(file_full_path) LIKE '%огдип%' THEN 'ОГДиП'
        WHEN LOWER(file_full_path) LIKE '%окг%' THEN 'ОКГ'
        WHEN LOWER(file_full_path) LIKE '%эо%' THEN 'ЭО'
        WHEN LOWER(file_full_path) LIKE '%огифт%' THEN 'ОГиФТ'
        WHEN LOWER(file_full_path) LIKE '%сгм%' THEN 'СГМ'
        WHEN LOWER(file_full_path) LIKE '%юр. отдел%' OR LOWER(file_full_path) LIKE '%юо%' THEN 'ЮО'
        WHEN LOWER(file_full_path) LIKE '%илц%' THEN 'ИЛЦ'
        WHEN LOWER(file_full_path) LIKE '%сго%' THEN 'СГО'
        WHEN LOWER(file_full_path) LIKE '%окс%' OR LOWER(file_full_path) LIKE '%конктракт%' THEN 'ОКС'
        WHEN LOWER(file_full_path) LIKE '%охоимтс%' THEN 'охоимтс'
        WHEN LOWER(file_full_path) LIKE '%оодц%' THEN 'ООДЦ'
        WHEN LOWER(file_full_path) LIKE '%бухгалтерия%' THEN 'бухгалтерия'
        WHEN LOWER(file_full_path) LIKE '%кадры%' OR LOWER(file_full_path) LIKE '%отдел кадров%' OR LOWER(file_full_path) LIKE '%ок%' THEN 'ОК'
        WHEN LOWER(file_full_path) LIKE '%администрация%' THEN 'администрация'
        ELSE 'Другое'
    END
ORDER BY "Отдел";
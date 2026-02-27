-- Сначала создадим временную таблицу с отделами
DROP TABLE IF EXISTS temp_depts;
CREATE TEMP TABLE temp_depts AS
SELECT 
    CASE 
        WHEN LOWER(file_full_path) LIKE '%отделение гигиены детей и подростков%' OR LOWER(file_full_path) LIKE '%огдип%' THEN 'ОГДиП'
        WHEN LOWER(file_full_path) LIKE '%отделение коммунальной гигиены%' OR LOWER(file_full_path) LIKE '%окг%' THEN 'ОКГ'
        WHEN LOWER(file_full_path) LIKE '%отделение гигиены и физиологии труда%' OR LOWER(file_full_path) LIKE '%огифт%' THEN 'ОГиФТ'
        WHEN LOWER(file_full_path) LIKE '%отделение гигиены питания%' OR LOWER(file_full_path) LIKE '%огп%' THEN 'ОГП'
        WHEN LOWER(file_full_path) LIKE '%санитарно-гигиенический отдел%' THEN 'СГО'
        WHEN LOWER(file_full_path) LIKE '%кемеровский филиал жд%' THEN 'ОЖД'
        WHEN LOWER(file_full_path) LIKE '%эпидемиологический отдел%' OR LOWER(file_full_path) LIKE '%эо%' THEN 'ЭО'
        WHEN LOWER(file_full_path) LIKE '%планово-экономический отдел%' THEN 'ПЭО'
        WHEN LOWER(file_full_path) LIKE '%отдел кадров%' THEN 'ОК'
        WHEN LOWER(file_full_path) LIKE '%руководящие документы%' THEN 'Руководящие документы'
        WHEN LOWER(file_full_path) LIKE '%отделение социально-гигиенического мониторинга%' THEN 'СГМ'
        WHEN LOWER(file_full_path) LIKE '%отделение гигиенического воспитания и аттестации%' THEN 'ОГВиА'
        WHEN LOWER(file_full_path) LIKE '%отделение информационно-технического обеспечения%' THEN 'ОИТО'
        WHEN LOWER(file_full_path) LIKE '%юридический отдел%' OR LOWER(file_full_path) LIKE '%юо%' THEN 'ЮО'
        WHEN LOWER(file_full_path) LIKE '%илц%' THEN 'ИЛЦ'
        WHEN LOWER(file_full_path) LIKE '%контрактная служба%' OR LOWER(file_full_path) LIKE '%конктракт%' THEN 'ОКС'
        WHEN LOWER(file_full_path) LIKE '%охоимтс%' THEN 'ОХОиМТС'
        WHEN LOWER(file_full_path) LIKE '%бухгалтерия%' THEN 'БУХ'
        WHEN LOWER(file_full_path) LIKE '%администрация%' THEN 'АДМ'
        WHEN LOWER(file_full_path) LIKE '%оодц%' THEN 'ООДЦ'
        WHEN LOWER(file_full_path) LIKE '%кадры%' OR LOWER(file_full_path) LIKE '%ок%' THEN 'ОК'
        ELSE 'другое'
    END as dept_name,
    file_compression_kbites,
    file_pages,
    file_origin_size_kbytes
FROM processed_files;

-- Отделы с итогами (обернуто в подзапрос для ORDER BY)
SELECT * FROM (
    SELECT 
        dept_name as "Отдел",
        COUNT(*) as "Количество файлов",
        ROUND(AVG(file_compression_kbites / 1024.0), 3) as "Средний объем сжатия, МБ",
        ROUND(SUM(file_compression_kbites / 1024.0), 3) as "Суммарный объем сжатия, МБ",
        ROUND(MIN(file_compression_kbites / 1024.0), 3) as "Минимальный объем сжатия, МБ",
        ROUND(MAX(file_compression_kbites / 1024.0), 3) as "Максимальный объем сжатия, МБ",
        SUM(file_pages) as "Сумма страниц, шт.",
        ROUND(AVG(file_pages), 1) as "Среднее страниц, шт.",
        ROUND(MIN(file_pages), 1) as "Мин страниц, шт.",
        ROUND(MAX(file_pages), 1) as "Макс страниц, шт.",
        ROUND(AVG(CASE WHEN file_pages > 0 THEN file_origin_size_kbytes * 1.0 / file_pages ELSE 0 END), 3) as "Среднее КБ/стр.",
        ROUND(MIN(CASE WHEN file_pages > 0 THEN file_origin_size_kbytes * 1.0 / file_pages ELSE 0 END), 3) as "Мин КБ/стр.",
        ROUND(MAX(CASE WHEN file_pages > 0 THEN file_origin_size_kbytes * 1.0 / file_pages ELSE 0 END), 3) as "Макс КБ/стр."
    FROM temp_depts
    GROUP BY dept_name
    
    UNION ALL
    
    SELECT 
        'ИТОГО:',
        COUNT(*),
        '-',
        ROUND(SUM(file_compression_kbites / 1024.0), 3),
        '-',
        '-',
        SUM(file_pages),
        '-',
        '-',
        '-',
        '-',
        '-',
        '-'
    FROM temp_depts
) AS result
ORDER BY 
    CASE WHEN "Отдел" = 'ИТОГО:' THEN 1 ELSE 0 END,
    "Отдел";

-- Удаляем временную таблицу
-- DROP TABLE IF EXISTS temp_depts;
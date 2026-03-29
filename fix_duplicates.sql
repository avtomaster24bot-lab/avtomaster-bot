(
echo PRAGMA foreign_keys=OFF;
echo BEGIN TRANSACTION;
echo UPDATE station_categories 
echo SET category_id = (
echo     SELECT MIN(c2.id) 
echo     FROM categories c2 
echo     WHERE c2.name = (SELECT c3.name FROM categories c3 WHERE c3.id = station_categories.category_id) 
echo       AND c2.city_id = (SELECT id FROM cities WHERE name = 'Талдыкорган')
echo )
echo WHERE station_id IN (SELECT id FROM stations);
echo DELETE FROM categories 
echo WHERE id NOT IN (
echo     SELECT MIN(id) 
echo     FROM categories 
echo     WHERE city_id = (SELECT id FROM cities WHERE name = 'Талдыкорган')
echo     GROUP BY name
echo );
echo COMMIT;
echo PRAGMA foreign_keys=ON;
) > fix_duplicates.sql
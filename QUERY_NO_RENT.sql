-- Query to get all no-rent items
-- Run this with: mysql -u root -p peq < QUERY_NO_RENT.sql > no_rent_items.txt
-- Then run: python generate_no_rent_list.py no_rent_items.txt

SELECT id FROM items WHERE norent = 0 ORDER BY id;

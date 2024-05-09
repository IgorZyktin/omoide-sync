# omoide-sync

Инструмент автоматической синхронизации каталогов для
проекта [Omoide](https://github.com/IgorZyktin/omoide).

## Что делает

Проект `Omoide` упрощает хранение и поиск сохранённых картинок, например -
смешных фотографий с котами. Когда фотографий становится много, а вы, при этом,
продолжаете их сохранять, в какой-то момент становится просто неудобно
постоянно заходить на сайт для обновления коллекции.

Данный сервис упрощает процесс, синхронизируя локальный каталог с вашим
аккаунтом на сайте. Вы сохраняете картинки на свой компьютер, а `omoide-sync`
сам загружает их на сайт.

## Как работает

Вам надо сообщить сервису за каким каталогом следить, а также предоставить
логин и пароль для вашего пользователя на сайте (или сразу нескольких
пользователей). Когда он запустится, он проверит вложенные каталоги и файлы и,
при обнаружении новых, загрузит их на сайт.

Сервис выполнен в виде скрипта, его можно запускать вручную или делать это
автоматическими средствами (например через `cron`).

Каталог отслеживания должен быть структурирован следующим образом:

```
Корневой каталог
├───Пользователь 1
│   └───Смешные коты
│       ├───Картинка1.jpg
│       └───Картинка2.jpg
└───Пользователь 2
    └───Фотографии с жабами
        ├───Картинка1.jpg
        └───Картинка2.jpg
```

На верхнем уровне должны находиться каталоги пользователей. Минимум один, но
также поддерживается несколько пользователей (если у вас есть несколько
несвязанных друг с другом больших тем для картинок).

Внутри пользователей может быть сколько угодно вложенных папок с картинками.
Имя каталога должно строго совпадать с названием коллекции. Сервис будет
сравнивать содержимое каталога с данными на сайте и, при необходимости, будет
создавать на сайте новые коллекции. Удалять данные сервис не умеет, он
используется только для добавления новых картинок и коллекций.

После того как сервис загрузит данные, он может сразу удалить их или же
переместить в каталог для удалённых файлов. При настройке надо указать, какой
тип удаления использовать и какой каталог использовать в качестве
корзины. Данные будут перенесены в неё таким образом, чтобы сохранялась
структура каталогов. Вы можете самостоятельно удалять данные из корзины, когда
удостоверитесь, что всё сохранено и локальная копия вам больше не нужна.

## Настройка коллекций

Настройка сервиса идёт через размещение файлов `config.yaml` в каталогах. Этот
файл распространяет своё действие на каталог и все вложенные каталоги. Но если
во вложенной папке будет ещё один такой файл, он может выставить новое значение
параметров. Разместив несколько таких файлов в нужных местах, вы можете
настроить поведение сразу множества каталогов.

Пример `config.yaml`:

```yaml
deletion_strategy_folder: delete
deletion_strategy_file: delete
treat_as_collection: true
tags: [ ]
```

#### deletion_strategy_folder/deletion_strategy_file

Что делать с файлами и каталогами после загрузки. Используя эту настройку, вы
можете создать неудаляемые коллекции. Например, если вы постоянно сохраняете
фото с котами, скорее всего вы захотите, чтобы этот каталог всегда был на
месте, чтобы в него можно было добавить новые фото.

Возможные варианты:

* move - переместит в каталог для удалённых материалов (значение по умолчанию).
* delete - сразу удалить.
* nothing - ничего не делать.

Учтите, что если выставлено удаление каталога, вариант `nothing` для файлов
будет проигнорирован.

#### treat_as_collection

Рассматривать каталог как коллекцию. Значение по умолчанию `true`. Вы можете
выставить его в `false`, если хотите, чтобы картинки в каталоге были включены в
родительскую коллекцию. Имя каталога при этом будет проигнорировано.

Это нужно для случаев, если у вас есть большая коллекция, например `Коты`. Но
внутри коллекции вам хотелось бы дополнительно промаркировать картинки тегами,
но всё же не разделять их на разные коллекции.

Пример структуры каталога:

```
Коты
├───config.yaml
├───Коты толстые
│   ├───config.yaml
│   ├───Картинка1.jpg
│   └───Картинка2.jpg
└───Коты рыжие
    ├───config.yaml
    ├───Картинка1.jpg
    └───Картинка2.jpg
```

Таким образом вы получите одну коллекцию `Коты`, но картинки в этой коллекции
смогут иметь разные дополнительные теги.

### Управление тегами

Для выставления дополнительных тегов, в `config.yaml` надо заполнить
ключ `tags`.
Каждый тег будет потом унаследован всеми вложенными каталогами и картинками.

Пример заполнения:

```yaml
tags:
 - толстые коты
 - меховой шар
 - жиробас
```

## Настройка сервиса

Сервис настраивается через переменные окружения.

Пример настройки:

```shell
# адрес сайта для загрузки данных
OMOIDE_SYNC__URL=https://omoide.ru
# каталог с картинками
OMOIDE_SYNC__ROOT=/home/user/pictures
# корзина для загруженных файлов
OMOIDE_SYNC__TRASH=/home/user/pictures_uploaded
# тип аутентификации, поддерживается только JSON
OMOIDE_SYNC__AUTH_TYPE=JSON
# набор пар `имя пользователя`:`пароль`
OMOIDE_SYNC__AUTH_DATA='{"some-user": "some-password"}'
```

## Запуск сервиса

Раздел требует доработки.

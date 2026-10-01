import type { Language } from "@/lib/i18n";

export type HelpTopicId =
  | "dashboard"
  | "netWorth"
  | "investments"
  | "roi"
  | "transactions"
  | "statementImport"
  | "accounts"
  | "categories"
  | "rules"
  | "cashFlow"
  | "reports"
  | "budgets"
  | "envelopes"
  | "recurring"
  | "goals"
  | "advice"
  | "settings";

export interface LocalizedText {
  ru: string;
  en: string;
}

export interface HelpTopic {
  id: HelpTopicId;
  path: string;
  title: LocalizedText;
  purpose: LocalizedText;
  whenToUse: LocalizedText;
  example: LocalizedText;
  misunderstanding: LocalizedText;
}

export const HELP_TOPICS: HelpTopic[] = [
  {
    id: "dashboard",
    path: "/",
    title: { ru: "Дашборд", en: "Dashboard" },
    purpose: { ru: "Краткая картина текущего месяца: доходы, расходы, остаток, норма сбережений и последние операции.", en: "A quick picture of the current month: income, spending, net result, savings rate, and recent activity." },
    whenToUse: { ru: "Открывайте для ежедневной проверки, всё ли идёт по плану.", en: "Open it for a daily check that your money is moving as planned." },
    example: { ru: "Если расходы растут быстрее доходов, дашборд покажет это до конца месяца.", en: "If spending starts growing faster than income, the dashboard makes it visible before month end." },
    misunderstanding: { ru: "Это обзор, а не отдельный источник данных: цифры складываются из счетов и транзакций.", en: "It is an overview, not a separate source of data: its figures come from accounts and transactions." },
  },
  {
    id: "netWorth",
    path: "/net-worth",
    title: { ru: "Капитал", en: "Net worth" },
    purpose: { ru: "Показывает стоимость всех денег и имущества за вычетом обязательств и её изменение со временем.", en: "Shows the value of all your money and property minus obligations, and how it changes over time." },
    whenToUse: { ru: "Добавляйте крупные активы и периодически обновляйте их оценку.", en: "Use it to track major assets and update their value periodically." },
    example: { ru: "Депозит, квартира и автомобиль дают общую картину капитала, даже если по ним нет обычных транзакций.", en: "A deposit, home, and car contribute to the full picture even when they have no everyday transactions." },
    misunderstanding: { ru: "Баланс счетов — только часть капитала; рыночная оценка актива не означает доступные для трат деньги.", en: "Account balances are only part of net worth; an asset valuation is not cash available to spend." },
  },
  {
    id: "investments",
    path: "/investments",
    title: { ru: "Инвестиции", en: "Investments" },
    purpose: { ru: "Учитывает портфели, сделки, дивиденды, себестоимость и финансовый результат по бумагам.", en: "Tracks portfolios, trades, dividends, cost basis, and investment results." },
    whenToUse: { ru: "Используйте после создания инвестиционного счёта и при каждой покупке, продаже или выплате.", en: "Use it after creating an investment account and whenever you buy, sell, or receive a payout." },
    example: { ru: "Покупка 10 акций, комиссия брокера и поздний дивиденд формируют результат одной позиции.", en: "A purchase of 10 shares, its broker fee, and a later dividend all contribute to one position's result." },
    misunderstanding: { ru: "Текущая цена не заменяет историю сделок и не является гарантией будущей доходности.", en: "A current price does not replace trade history and does not guarantee future returns." },
  },
  {
    id: "roi",
    path: "/roi",
    title: { ru: "Доходность", en: "Returns" },
    purpose: { ru: "Сравнивает результат инвестиций с вложенной суммой и показывает доходность за выбранный период.", en: "Compares investment results with the amount invested and shows returns for the selected period." },
    whenToUse: { ru: "Используйте после внесения сделок, комиссий и выплат, чтобы оценивать портфель по фактическим данным.", en: "Use it after recording trades, fees, and payouts to evaluate the portfolio from actual data." },
    example: { ru: "Если позиция выросла в цене, но по ней были комиссии, доходность покажет итоговый результат с учётом этих затрат.", en: "If a position gained value but incurred fees, Returns shows the resulting performance after those costs." },
    misunderstanding: { ru: "Доходность за прошлый период не гарантирует такой же результат в будущем и зависит от полноты истории операций.", en: "Past returns do not guarantee future results and depend on a complete transaction history." },
  },
  {
    id: "transactions",
    path: "/transactions",
    title: { ru: "Транзакции и импорт", en: "Transactions and import" },
    purpose: { ru: "Хранит доходы, расходы и переводы; импорт помогает перенести операции из банковской выписки.", en: "Stores income, expenses, and transfers; import brings transactions in from a bank statement." },
    whenToUse: { ru: "Добавляйте операции вручную или загружайте выписку, затем проверяйте результат до сохранения.", en: "Add activity manually or upload a statement, then review the result before saving." },
    example: { ru: "Один чек можно разделить между продуктами и бытовыми товарами, не создавая две покупки.", en: "One receipt can be split between groceries and household supplies without creating two purchases." },
    misunderstanding: { ru: "Перевод между своими счетами — не доход и не расход; импорт не следует подтверждать без проверки.", en: "A transfer between your own accounts is neither income nor spending; imported rows still need review." },
  },
  {
    id: "statementImport",
    path: "/transactions/import",
    title: { ru: "Импорт банковской выписки", en: "Bank statement import" },
    purpose: { ru: "Распознаёт операции из загруженной выписки и готовит их к проверке до добавления в Aurum.", en: "Recognizes activity from an uploaded statement and prepares it for review before anything is added to Aurum." },
    whenToUse: { ru: "Загрузите поддерживаемый файл, проверьте каждую распознанную строку, исправьте данные и выберите только нужные операции.", en: "Upload a supported file, review every recognized row, correct the data, and select only the activity you want." },
    example: { ru: "После загрузки PDF проверьте дату, сумму, счёт и категорию каждой строки; только затем нажмите «Импортировать».", en: "After uploading a PDF, check each row's date, amount, account, and category before pressing Import." },
    misunderstanding: { ru: "Предпросмотр ничего не записывает. Операции попадут в журнал только после явного нажатия «Импортировать».", en: "Preview saves nothing. Nothing reaches the ledger until you press Import explicitly." },
  },
  {
    id: "accounts",
    path: "/accounts",
    title: { ru: "Счета", en: "Accounts" },
    purpose: { ru: "Отражает места, где лежат деньги: карты, наличные, вклады и инвестиционные счета.", en: "Represents where money is held: cards, cash, deposits, and investment accounts." },
    whenToUse: { ru: "Создайте по одному счёту для каждого реального источника баланса и выберите правильную валюту.", en: "Create one for each real balance source and choose its actual currency." },
    example: { ru: "Отдельные счета для карты в KZT и депозита в USD сохраняют валюты и переводы понятными.", en: "Separate KZT card and USD deposit accounts keep currencies and transfers clear." },
    misunderstanding: { ru: "Счёт — не категория расхода: он отвечает на вопрос «где деньги», а не «на что потрачены».", en: "An account is not a spending category: it answers “where is the money,” not “what was it spent on.”" },
  },
  {
    id: "categories",
    path: "/categories",
    title: { ru: "Категории", en: "Categories" },
    purpose: { ru: "Группирует доходы и расходы по смыслу, чтобы отчёты и бюджеты были полезными.", en: "Groups income and spending by meaning so reports and budgets are useful." },
    whenToUse: { ru: "Создавайте устойчивые группы, которыми будете пользоваться много месяцев.", en: "Create stable groups you expect to use for many months." },
    example: { ru: "В категории «Еда» могут быть подкатегории «Продукты» и «Кафе».", en: "A Food category can contain Groceries and Eating out subcategories." },
    misunderstanding: { ru: "Слишком много узких категорий усложняет анализ; для разовых деталей лучше заметки или теги.", en: "Too many narrow categories make analysis harder; use notes or tags for one-off detail." },
  },
  {
    id: "rules",
    path: "/rules",
    title: { ru: "Правила категоризации", en: "Categorization rules" },
    purpose: { ru: "Автоматически предлагает категорию по тексту операции и дополнительным условиям.", en: "Automatically suggests a category from transaction text and optional conditions." },
    whenToUse: { ru: "Создавайте правило для регулярно повторяющихся описаний от одного продавца или источника.", en: "Create one for descriptions that repeatedly come from the same merchant or source." },
    example: { ru: "Описание с «Coffee House» можно направлять в «Кафе», а затем проверить подходящие операции перед применением.", en: "A description containing “Coffee House” can go to Eating out, then you can preview matching transactions before applying it." },
    misunderstanding: { ru: "Порядок важен: при нескольких совпадениях сработает первое подходящее правило; проверка ничего не меняет.", en: "Order matters: when several rules match, the first suitable one wins; previewing changes nothing." },
  },
  {
    id: "cashFlow",
    path: "/cash-flow",
    title: { ru: "Движение денег", en: "Cash flow" },
    purpose: { ru: "Сравнивает реальные доходы и расходы по месяцам.", en: "Compares actual income and spending month by month." },
    whenToUse: { ru: "Ищите месяцы с дефицитом и проверяйте, устойчив ли положительный остаток.", en: "Use it to spot deficit months and check whether positive cash flow is sustainable." },
    example: { ru: "Три месяца подряд с расходами выше доходов показывают проблему, даже если общий баланс пока высокий.", en: "Three months of spending above income reveal a problem even if the total balance is still high." },
    misunderstanding: { ru: "Рост капитала из-за переоценки имущества не является денежным доходом.", en: "An increase in an asset valuation is not cash income." },
  },
  {
    id: "reports",
    path: "/reports",
    title: { ru: "Отчёты", en: "Reports" },
    purpose: { ru: "Показывает, какие категории забирают больше денег и как траты меняются во времени.", en: "Shows which categories use the most money and how spending changes over time." },
    whenToUse: { ru: "Сравнивайте периоды перед изменением бюджета или финансовых привычек.", en: "Compare periods before changing a budget or financial habit." },
    example: { ru: "Сравнение расходов на кафе за этот и прошлый год помогает оценить тренд, а не одну случайную покупку.", en: "Comparing Eating out this year and last year reveals a trend rather than one unusual purchase." },
    misunderstanding: { ru: "Отчёт отражает качество категорий и введённых операций; пропущенные данные искажают выводы.", en: "A report is only as accurate as its categories and transactions; missing data distorts conclusions." },
  },
  {
    id: "budgets",
    path: "/budget",
    title: { ru: "Бюджеты", en: "Budgets" },
    purpose: { ru: "Задаёт месячный предел расходов для выбранной категории и показывает прогресс.", en: "Sets a monthly spending limit for a category and shows progress against it." },
    whenToUse: { ru: "Используйте для категорий, где важен простой потолок расходов.", en: "Use it for categories where a simple monthly ceiling is enough." },
    example: { ru: "Лимит 60 000 ₸ на кафе покажет, какая его часть уже потрачена в этом месяце.", en: "A 60,000 ₸ Eating out limit shows how much has already been used this month." },
    misunderstanding: { ru: "Бюджет не резервирует деньги и не переносит остаток автоматически — для этого нужны конверты.", en: "A budget does not reserve money or automatically carry it forward; use envelopes for that." },
  },
  {
    id: "envelopes",
    path: "/envelopes",
    title: { ru: "Конверты", en: "Envelopes" },
    purpose: { ru: "Заранее назначьте каждому тенге дохода задачу, чтобы сумма всех планов не превышала доступные деньги.", en: "Give every unit of income a job before you spend it, so all plans stay within the money available." },
    whenToUse: { ru: "Используйте для бюджета с нулевой базой: распределите доступную сумму по категориям и переносите остатки между месяцами.", en: "Use it for zero-based budgeting: assign available money to categories and carry balances between months." },
    example: { ru: "Из 300 000 ₸ назначьте 120 000 ₸ на жильё, 80 000 ₸ на продукты, 40 000 ₸ в резерв и распределите остальные 60 000 ₸.", en: "From 300,000 ₸, assign 120,000 ₸ to housing, 80,000 ₸ to groceries, 40,000 ₸ to a reserve, and give the remaining 60,000 ₸ another job." },
    misunderstanding: { ru: "План не переводит деньги между банковскими счетами и не создаёт расход: он только назначает цель уже доступным деньгам.", en: "A plan does not move money between bank accounts or create spending; it only assigns a purpose to money already available." },
  },
  {
    id: "recurring",
    path: "/recurring",
    title: { ru: "Регулярные платежи", en: "Recurring payments" },
    purpose: { ru: "Хранит шаблоны повторяющихся счетов, подписок и поступлений вместе со следующей датой.", en: "Keeps templates for repeating bills, subscriptions, and income with the next due date." },
    whenToUse: { ru: "Добавляйте предсказуемые операции, чтобы не забывать их и быстро проводить в нужный день.", en: "Add predictable activity so it is not forgotten and can be posted quickly when due." },
    example: { ru: "Ежемесячную аренду можно провести одним нажатием, когда платёж действительно состоялся.", en: "A monthly rent payment can be posted with one action when it actually happens." },
    misunderstanding: { ru: "Aurum не списывает деньги и не создаёт транзакции в фоне без вашего действия.", en: "Aurum does not move money or create transactions in the background without your action." },
  },
  {
    id: "goals",
    path: "/goals",
    title: { ru: "Цели", en: "Goals" },
    purpose: { ru: "Показывает прогресс накопления к конкретной сумме и сроку.", en: "Tracks saving progress toward a specific amount and target date." },
    whenToUse: { ru: "Создайте цель для крупной покупки, резерва или другого измеримого результата.", en: "Create one for a major purchase, emergency reserve, or another measurable outcome." },
    example: { ru: "Для резерва 1 200 000 ₸ фиксируйте каждое пополнение и следите за оставшейся суммой.", en: "For a 1,200,000 ₸ emergency fund, record each contribution and track the amount remaining." },
    misunderstanding: { ru: "Запись взноса обновляет прогресс цели, но сама по себе не переводит деньги на отдельный счёт.", en: "Recording a contribution updates goal progress but does not itself transfer money to another account." },
  },
  {
    id: "advice",
    path: "/advice",
    title: { ru: "Советы", en: "Advice" },
    purpose: { ru: "Находит заметные изменения в расходах, бюджетах и норме сбережений.", en: "Finds notable changes in spending, budgets, and savings rate." },
    whenToUse: { ru: "Просматривайте после обновления данных, чтобы заметить тенденции, требующие внимания.", en: "Review it after updating your data to spot trends that may need attention." },
    example: { ru: "Совет может отметить категорию, которая несколько месяцев растёт быстрее обычного.", en: "Advice can flag a category that has grown faster than usual for several months." },
    misunderstanding: { ru: "Это подсказки на основе ваших данных, а не персональная инвестиционная или налоговая рекомендация.", en: "These are prompts based on your data, not personal investment or tax advice." },
  },
  {
    id: "settings",
    path: "/settings",
    title: { ru: "Настройки", en: "Settings" },
    purpose: { ru: "Управляет языком, темой, основной валютой, порогами предупреждений и резервными копиями.", en: "Controls language, theme, primary currency, alert thresholds, and backups." },
    whenToUse: { ru: "Настройте интерфейс при первом запуске и экспортируйте копию перед рискованными изменениями.", en: "Set up the interface on first use and export a backup before risky changes." },
    example: { ru: "Можно выбрать English, тёмную тему и KZT как основную валюту отображения.", en: "You can choose Russian, dark mode, and KZT as the primary display currency." },
    misunderstanding: { ru: "Смена основной валюты меняет отображение, но не переписывает исходные суммы операций.", en: "Changing the primary currency changes display, not the original amounts of past transactions." },
  },
];

export function getHelpTopic(id: HelpTopicId): HelpTopic {
  const topic = HELP_TOPICS.find((item) => item.id === id);
  if (!topic) throw new Error(`Unknown help topic: ${id}`);
  return topic;
}

export function localize(text: LocalizedText, language: Language): string {
  return text[language];
}

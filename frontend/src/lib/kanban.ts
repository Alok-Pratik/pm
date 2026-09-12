export type Card = {
  id: string;
  title: string;
  details: string;
};

export type Column = {
  id: string;
  title: string;
  cardIds: string[];
};

export type BoardData = {
  id: string;
  title: string;
  columns: Column[];
  cards: Record<string, Card>;
};

export type BoardSummary = {
  id: string;
  title: string;
};

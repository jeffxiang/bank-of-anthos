export interface JwtClaims {
  user: string;
  acct: string;
  name: string;
  iat: number;
  exp: number;
}
export interface LoginResponse { token: string; }
export interface Contact {
  label: string;
  account_num: string;
  routing_num: string;
  is_external: boolean;
}
export interface Transaction {
  fromAccountNum: string;
  fromRoutingNum: string;
  toAccountNum: string;
  toRoutingNum: string;
  amount: number;
  timestamp: string;
}

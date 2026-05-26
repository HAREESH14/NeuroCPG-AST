import java.util.Scanner;

public class Main {
    public static long powFast(long base, int exp) {
        long res = 1;
        while (exp > 0) {
            if ((exp & 1) == 1) res *= base;
            base *= base;
            exp >>= 1;
        }
        return res;
    }

    public static void main(String[] args) {
        Scanner scanner = new Scanner(System.in);
        int n = scanner.nextInt();
        for (int i = 0; i < n; ++i) {
            long base = scanner.nextLong();
            int exp = scanner.nextInt();
            System.out.println(base + "^" + exp + " = " + powFast(base, exp));
        }
        scanner.close();
    }
}
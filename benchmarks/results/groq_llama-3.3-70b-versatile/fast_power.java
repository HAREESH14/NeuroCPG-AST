import java.util.Scanner;

public class FastPower {
    public static long fastPow(long base, long exp) {
        long result = 1;
        long b = base;
        while (exp > 0) {
            if ((exp & 1) == 1) result *= b;
            b *= b;
            exp >>= 1;
        }
        return result;
    }

    public static void main(String[] args) {
        Scanner scanner = new Scanner(System.in);
        long b = scanner.nextLong();
        long e = scanner.nextLong();
        System.out.println(b + "^" + e + " = " + fastPow(b, e));
    }
}
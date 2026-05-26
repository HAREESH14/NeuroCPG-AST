import java.util.Scanner;

public class TrailingZeros {
    public static int trailingZeros(int n) {
        int count = 0;
        for (int i = 5; i <= n; i *= 5) count += n / i;
        return count;
    }

    public static void main(String[] args) {
        Scanner scanner = new Scanner(System.in);
        int nums = scanner.nextInt();
        for (int i = 0; i < nums; ++i) {
            int n = scanner.nextInt();
            System.out.println("Trailing zeros in " + n + "! = " + trailingZeros(n));
        }
        scanner.close();
    }
}